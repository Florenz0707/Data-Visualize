register_map = {
    # Map tool names to module paths (modules will self-register classes via @register_tool)
    'qwen': 'modality_agents.llm',
    'qa_outline_story_writer': 'modality_agents.story_agent',
    'musicgen_t2m': 'MusicGenAgent',  # placeholder if needed
    'story_diffusion_t2i': 'modality_agents.image_agent',
    'cosyvoice_tts': 'CosyVoiceAgent',  # placeholder if needed
    'audioldm2_t2a': 'AudioLDM2Agent',  # placeholder if needed
    'slideshow_video_compose': 'video_compose_agent',
    'freesound_sfx_retrieval': 'FreesoundSfxAgent',  # placeholder if needed
    'freesound_music_retrieval': 'FreesoundMusicAgent',  # placeholder if needed
    'speech_generation': 'modality_agents.speech_agent',
}


def import_from_register(key):
    value = register_map[key]
    # Support both direct class import from package root and module path import
    if '.' in value:
        exec(f'from .{value} import *')
    else:
        exec(f'from . import {value}')


class ToolRegistry(dict):

    def _import_key(self, key):
        try:
            import_from_register(key)
        except Exception as e:
            print(f'import {key} failed, details: {e}')

    def __getitem__(self, key):
        if key not in self.keys():
            self._import_key(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self._import_key(key)
        return super().__contains__(key)


TOOL_REGISTRY = ToolRegistry()


def register_tool(name):
    def decorator(cls):
        TOOL_REGISTRY[name] = cls
        return cls

    return decorator


def init_tool_instance(cfg):
    return TOOL_REGISTRY[cfg["tool"]](cfg["cfg"])

