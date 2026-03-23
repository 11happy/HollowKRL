import time
import gymnasium as gym
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from env import HollowKnightEnv
from stable_baselines3.common.monitor import Monitor



def make_env():
    def _init():
        env = HollowKnightEnv()
        return env
    return _init


print("Setting up environment...")


env = DummyVecEnv([lambda: Monitor(HollowKnightEnv())])
env = VecNormalize(
    env,
    norm_obs    = True,   
    norm_reward = True,   
    clip_obs    = np.inf,    
    clip_reward = np.inf,  
)

# ── PPO Model ─────────────────────────────────────────────────
model = PPO(
    policy          = "MlpPolicy",
    env             = env,
    learning_rate   = 5e-4,
    n_steps         = 2048,      
    batch_size      = 256,
    n_epochs        = 10,
    gamma           = 0.99,
    gae_lambda      = 0.95, 
    clip_range      = 0.2,
    vf_coef         = 0.5,
    ent_coef        = 0.025,     
    verbose         = 1,
    tensorboard_log = "./logs/",
    device          = "cpu",   
)


checkpoint_cb = CheckpointCallback(
    save_freq       = 20_000,
    save_path       = "./checkpoints_3/",
    name_prefix     = "ppo_hornet_4",
    save_vecnormalize = True,
)


print("Starting training...")
print("Make sure HK is open and focused on Hornet fight room.")
print("Training will begin in 5 seconds...")
time.sleep(5)

model.learn(
    total_timesteps    = 1000000,
    callback           = checkpoint_cb,
    reset_num_timesteps= True,
    tb_log_name        = "ppo_hornet_4",
)


model.save("checkpoints_3/ppo_hornet_4")
env.save("checkpoints_3/vecnormalize_final.pkl")
print("Training complete. Model saved.")