import argparse
import yaml
from mm_story_agent import MMStoryAgent
from mm_story_agent.config import load_env

# 在程序启动时加载环境变量
load_env()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="MM-StoryAgent: Generate storytelling videos from a configuration file.")
    parser.add_argument("--config", "-c", type=str, default="configs/mm_story_agent.yaml", 
                       help="Path to the main configuration file (default: configs/mm_story_agent.yaml)")
    parser.add_argument("--resume", "-r", action="store_true", 
                       help="Resume generation, skipping steps for which output files already exist.")

    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)
    
    # 获取模型配置文件路径（如果指定）
    models_config_path = config.get("models_config", "configs/models.yaml")
    
    # Pass the resume flag to the agent's constructor
    mm_story_agent = MMStoryAgent(models_config_path=models_config_path, resume=args.resume)
    
    # The agent will now handle the resume logic internally
    mm_story_agent.call(config)
