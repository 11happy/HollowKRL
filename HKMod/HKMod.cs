using Modding;
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace HKMod
{
    internal class HKMod : Mod
    {
        internal static HKMod Instance { get; private set; }

        // ── Game state ────────────────────────────────────────────
        private int   _playerHp    = 0;
        private int   _playerMaxHp = 0;
        private int   _bossHp      = 0;
        private int   _bossMaxHp   = 0;
        private float _playerX     = 0f;
        private float _playerY     = 0f;
        private float _playerVx    = 0f;
        private float _playerVy    = 0f;
        private float _bossX       = 0f;
        private float _bossY       = 0f;
        private float _bossVx      = 0f;
        private float _bossVy      = 0f;
        private bool  _onGround    = false;

        // ── Threat state ──────────────────────────────────────────
        private bool  _threatActive = false;
        private float _threatDx     = 0f;
        private float _threatDy     = 0f;
        private float _threatVx     = 0f;
        private float _threatVy     = 0f;

        private readonly object _stateLock = new object();

        // ── Boss reference ────────────────────────────────────────
        private HealthManager _bossHM = null;

        // ── Threat scan cache ─────────────────────────────────────
        private DamageHero[] _cachedThreats = new DamageHero[0];

        // ── TCP ───────────────────────────────────────────────────
        private TcpListener _server;
        private Thread      _serverThread;
        private const int   PORT = 11000;

        public HKMod() : base("HKMod") { }
        public override string GetVersion() => "1.0.0";

        public override void Initialize()
        {
            Log("ENVMOD Initializing");
            Instance = this;

            ModHooks.AfterPlayerDeadHook += OnPlayerDead;
            On.HeroController.AddHealth  += OnPlayerHeal;
            On.HealthManager.TakeDamage  += OnBossTakeDamage;
            On.HealthManager.Die         += OnBossDie;
            On.GameManager.Update        += OnGameManagerUpdate;

            UnityEngine.SceneManagement.SceneManager.sceneLoaded += OnSceneLoaded;

            _serverThread = new Thread(ServerLoop) { IsBackground = true };
            _serverThread.Start();

            Log("ENVMOD initialized — TCP on port " + PORT);
        }

        // ── Main thread update ────────────────────────────────────
        private void OnGameManagerUpdate(On.GameManager.orig_Update orig, GameManager self)
        {
            orig(self);
            UpdateHeroState();
            UpdateThreatState();
        }

        // ── Player hooks ──────────────────────────────────────────
        private void OnPlayerDead()
        {
            lock (_stateLock)
            {
                _playerHp = 0;
            }
        }

        private void OnPlayerHeal(On.HeroController.orig_AddHealth orig,
                                   HeroController self, int amount)
        {
            orig(self, amount);
            lock (_stateLock)
            {
                if (PlayerData.instance != null)
                {
                    _playerHp    = PlayerData.instance.health;
                    _playerMaxHp = PlayerData.instance.maxHealth;
                }
            }
        }

        // ── Boss hooks ────────────────────────────────────────────
        private void OnBossTakeDamage(On.HealthManager.orig_TakeDamage orig,
                                       HealthManager self, HitInstance hit)
        {
            orig(self, hit);

            if (self.gameObject.layer != 11) return;
            if (self.hp <= 0) return;

            lock (_stateLock)
            {
                if (_bossHM == null && self.hp > 50)
                    _bossHM = self;
            }
        }

        private void OnBossDie(On.HealthManager.orig_Die orig,
                                HealthManager self, float? dir,
                                AttackTypes type, bool ignoreEvasion)
        {
            orig(self, dir, type, ignoreEvasion);

            if (self.gameObject.layer != 11) return;

            lock (_stateLock)
            {
                _bossHp  = 0;
                _bossHM  = null;
            }
        }

        // ── Scene loaded ──────────────────────────────────────────
        private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            lock (_stateLock)
            {
                _bossHp = _bossMaxHp = 0;
                _bossX  = _bossY = _bossVx = _bossVy = 0f;
                _bossHM       = null;
                _threatActive = false;
                _threatDx = _threatDy = _threatVx = _threatVy = 0f;
            }

            // Try to grab boss immediately at scene load
            foreach (var hm in GameObject.FindObjectsOfType<HealthManager>())
            {
                if (hm.gameObject.layer == 11 && hm.hp > 50)
                {
                    lock (_stateLock)
                    {
                        _bossHM    = hm;
                        _bossHp    = hm.hp;
                        _bossMaxHp = hm.hp;
                    }
                    break;
                }
            }

            Log($"Scene loaded: {scene.name}");
        }

        // ── Hero + boss state — main thread only ──────────────────
        private void UpdateHeroState()
        {
            HeroController hero = HeroController.instance;
            if (hero == null) return;

            var heroRb = hero.GetComponent<Rigidbody2D>();

            lock (_stateLock)
            {
                _playerX  = hero.transform.position.x;
                _playerY  = hero.transform.position.y;
                _playerVx = heroRb != null ? heroRb.velocity.x : 0f;
                _playerVy = heroRb != null ? heroRb.velocity.y : 0f;
                _onGround = hero.cState.onGround;

                // Always poll — no longer dependent on damage hook
                if (PlayerData.instance != null)
                {
                    _playerHp    = PlayerData.instance.health;
                    _playerMaxHp = PlayerData.instance.maxHealth;
                }

                if (_bossHM != null)
                {
                    _bossX = _bossHM.transform.position.x;
                    _bossY = _bossHM.transform.position.y;

                    var bossRb = _bossHM.GetComponent<Rigidbody2D>();
                    _bossVx = bossRb != null ? bossRb.velocity.x : 0f;
                    _bossVy = bossRb != null ? bossRb.velocity.y : 0f;

                    // Always poll boss HP
                    _bossHp = _bossHM.hp;
                    // Catch max on first valid frame if OnSceneLoaded missed it
                    if (_bossMaxHp == 0)
                        _bossMaxHp = _bossHM.hp;
                }
            }
        }

        // ── Threat state — main thread only ───────────────────────
        private void UpdateThreatState()
        {
            _cachedThreats = GameObject.FindObjectsOfType<DamageHero>();

            float px, py;
            lock (_stateLock)
            {
                px = _playerX;
                py = _playerY;
            }

            GameObject nearest   = null;
            float      minDistSq = float.MaxValue;

            foreach (var dh in _cachedThreats)
            {
                string goName = dh.gameObject.name;
                if (!goName.Contains("Needle") && !goName.Contains("Sphere Ball"))
                    continue;

                Collider2D col     = dh.GetComponent<Collider2D>();
                Vector2    closest = col != null
                    ? col.ClosestPoint(new Vector2(px, py))
                    : new Vector2(dh.transform.position.x, dh.transform.position.y);

                float ddx    = px - closest.x;
                float ddy    = py - closest.y;
                float distSq = ddx * ddx + ddy * ddy;

                if (distSq < minDistSq)
                {
                    minDistSq = distSq;
                    nearest   = dh.gameObject;
                }
            }

            lock (_stateLock)
            {
                if (nearest != null)
                {
                    Collider2D col     = nearest.GetComponent<Collider2D>();
                    Vector2    closest = col != null
                        ? col.ClosestPoint(new Vector2(px, py))
                        : new Vector2(nearest.transform.position.x,
                                      nearest.transform.position.y);

                    _threatActive = true;
                    _threatDx     = closest.x - px;
                    _threatDy     = closest.y - py;

                    var rb    = nearest.GetComponent<Rigidbody2D>();
                    _threatVx = rb != null ? rb.velocity.x : 0f;
                    _threatVy = rb != null ? rb.velocity.y : 0f;
                }
                else
                {
                    _threatActive = false;
                    _threatDx = _threatDy = _threatVx = _threatVy = 0f;
                }
            }
        }

        // ── TCP ───────────────────────────────────────────────────
        private void ServerLoop()
        {
            _server = new TcpListener(IPAddress.Loopback, PORT);
            _server.Start();
            Log("TCP listening on port " + PORT);

            while (true)
            {
                try
                {
                    TcpClient client = _server.AcceptTcpClient();
                    Log("Python connected");
                    new Thread(() => ClientLoop(client))
                        { IsBackground = true }.Start();
                }
                catch (Exception e)
                {
                    Log("Server error: " + e.Message);
                }
            }
        }

        private void ClientLoop(TcpClient client)
        {
            NetworkStream stream = client.GetStream();

            try
            {
                byte[] initial = Encoding.UTF8.GetBytes(BuildJson() + "\n");
                stream.Write(initial, 0, initial.Length);
            }
            catch { }

            while (client.Connected)
            {
                try
                {
                    byte[] data = Encoding.UTF8.GetBytes(BuildJson() + "\n");
                    stream.Write(data, 0, data.Length);
                    Thread.Sleep(16);
                }
                catch
                {
                    Log("Client disconnected");
                    break;
                }
            }

            client.Close();
        }

        // ── State snapshot ────────────────────────────────────────
        private string BuildJson()
        {
            int   playerHp, playerMaxHp, bossHp, bossMaxHp;
            float playerVx, playerVy;
            float playerX, playerY, bossX, bossY;
            float bossVx, bossVy, dx, dy;
            bool  onGround, threatActive;
            float threatDx, threatDy, threatVx, threatVy;

            lock (_stateLock)
            {
                playerHp    = _playerHp;
                playerMaxHp = _playerMaxHp;
                bossHp    = _bossHp == 0 && _bossMaxHp > 0 ? _bossMaxHp : _bossHp;
                bossMaxHp   = _bossMaxHp;
                playerX     = _playerX;
                playerY     = _playerY;
                playerVx    = _playerVx;
                playerVy    = _playerVy;
                bossX       = _bossX;
                bossY       = _bossY;
                bossVx      = _bossVx;
                bossVy      = _bossVy;
                dx          = bossX - playerX;
                dy          = bossY - playerY;
                onGround    = _onGround;
                threatActive= _threatActive;
                threatDx    = _threatDx;
                threatDy    = _threatDy;
                threatVx    = _threatVx;
                threatVy    = _threatVy;
            }

            return $"{{" +
                $"\"player_hp\":{playerHp}," +
                $"\"player_max_hp\":{playerMaxHp}," +
                $"\"player_vx\":{playerVx:F3}," +
                $"\"player_vy\":{playerVy:F3}," +
                $"\"on_ground\":{onGround.ToString().ToLower()}," +
                $"\"boss_hp\":{bossHp}," +
                $"\"boss_max_hp\":{bossMaxHp}," +
                $"\"dx\":{dx:F3}," +
                $"\"dy\":{dy:F3}," +
                $"\"boss_vx\":{bossVx:F3}," +
                $"\"boss_vy\":{bossVy:F3}," +
                $"\"threat_active\":{threatActive.ToString().ToLower()}," +
                $"\"threat_dx\":{threatDx:F3}," +
                $"\"threat_dy\":{threatDy:F3}," +
                $"\"threat_vx\":{threatVx:F3}," +
                $"\"threat_vy\":{threatVy:F3}" +
                $"}}";
        }
    }
}