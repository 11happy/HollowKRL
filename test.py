import time
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from env import HollowKnightEnv


def make_env():
    return HollowKnightEnv()

env = DummyVecEnv([make_env])


env = VecNormalize.load("/home/happy/HollowKRL/checkpoints_3/ppo_hornet_4_vecnormalize_820000_steps.pkl", env)


env.training = False
env.norm_reward = False   


model = PPO.load("/home/happy/HollowKRL/checkpoints_3/ppo_hornet_4_820000_steps.zip", env=env)


obs = env.reset()

for episode in range(10):
    done = False
    total_reward = 0

    while not done:
        action, _ = model.predict(obs, deterministic=False)

        obs, reward, done, info = env.step(action)
        total_reward += reward[0]

        time.sleep(0.05) 

    print(f"Episode {episode} reward:", total_reward)
    obs = env.reset()