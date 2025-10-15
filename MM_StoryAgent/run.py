import argparse
import yaml
from mm_story_agent import MMStoryAgent


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", type=str, required=True)
    parser.add_argument("--resume", "-r", action="store_true", 
                       help="Resume from video composition stage (skip story, speech, and image generation)")

    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)
    
    mm_story_agent = MMStoryAgent()
    
    if args.resume:
        print(" Resuming from video composition stage...")
        print(" Skipping: story generation, speech synthesis, image generation")
        print(" Starting: video composition only")
        mm_story_agent.resume_from_video_composition(config)
    else:
        mm_story_agent.call(config)
