# 配置文件说明

## 概述

MM-StoryAgent 使用两层配置系统：

1. **`models.yaml`** - 模型配置文件，定义所有可用的模型及其参数
2. **`mm_story_agent.yaml`** - 主配置文件，为每个agent指定使用的模型

## 配置文件结构

### 1. models.yaml - 模型配置

定义所有可用的模型，支持 OpenAI 和 DashScope (阿里云) 规范。

```yaml
llm_models:
  qwen2_72b:
    provider: dashscope
    model_name: qwen2-72b-instruct
    api_key_env: DASHSCOPE_API_KEY
    default_params:
      temperature: 0.7
      top_p: 0.95
      max_tokens: 4000

  gpt_4o:
    provider: openai
    model_name: gpt-4o
    api_key_env: OPENAI_API_KEY
    default_params:
      temperature: 0.7
      max_tokens: 4000

image_models:
  wanx_v1:
    provider: dashscope
    model_name: wanx-v1
    api_key_env: DASHSCOPE_API_KEY

  dalle_3:
    provider: openai
    model_name: dall-e-3
    api_key_env: OPENAI_API_KEY

speech_models:
  kokoro:
    provider: local
    model_name: kokoro
    repo_id: hexgrad/Kokoro-82M
    default_params:
      voice: af_heart
      sample_rate: 24000
```

#### 字段说明

- **provider**: 模型提供商 (`dashscope`, `openai`, `local`, `custom_api`, 等)
- **model_name**: 模型名称
- **api_key_env**: API密钥的环境变量名
- **api_base_env**: (可选) API端点的环境变量名
- **default_params**: 模型的默认参数

### 2. mm_story_agent.yaml - 主配置

为每个agent指定使用的模型。

```yaml
# 指定模型配置文件路径
models_config: configs/models.yaml

story_writer:
    tool: qa_outline_story_writer
    model: qwen2_72b  # 从 models.yaml 中选择
    cfg:
        max_conv_turns: 3
        temperature: 0.5  # 覆盖模型的默认参数
    params:
        story_topic: "Your story topic"

image_generation:
    tool: story_diffusion_t2i
    model: wanx_v1  # 图像生成模型
    llm_model: qwen_plus  # 用于生成提示词的LLM
    cfg:
        num_turns: 3
    params:
        style_name: "Japanese Anime"

speech_generation:
    tool: speech_generation
    model: kokoro  # TTS模型
    cfg:
        sample_rate: 24000  # 覆盖默认参数
    params:
        voice: "af_heart"
```

## 配置优先级

配置参数的优先级（从高到低）：

1. **agent的cfg** - 在 `mm_story_agent.yaml` 中agent的 `cfg` 部分
2. **模型的default_params** - 在 `models.yaml` 中模型的 `default_params`
3. **模型的其他配置** - 在 `models.yaml` 中模型的其他字段（provider, model_name等）

## 环境变量

需要设置以下环境变量（根据使用的模型）：

### DashScope (阿里云)
```bash
export DASHSCOPE_API_KEY="your-api-key"
export ALIYUN_ACCESS_KEY_ID="your-access-key-id"
export ALIYUN_ACCESS_KEY_SECRET="your-access-key-secret"
export ALIYUN_APP_KEY="your-app-key"
```

### OpenAI
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://api.openai.com/v1"  # 可选
```

### Stability AI
```bash
export STABILITY_API_KEY="your-api-key"
```

### Replicate
```bash
export REPLICATE_API_TOKEN="your-api-token"
```

### FreeSound
```bash
export FREESOUND_API_KEY="your-api-key"
```

## 使用示例

### 示例 1: 使用 DashScope 模型

```yaml
models_config: configs/models.yaml

story_writer:
    tool: qa_outline_story_writer
    model: qwen2_72b
    cfg:
        max_conv_turns: 3
    params:
        story_topic: "Learning about space"

image_generation:
    tool: story_diffusion_t2i
    model: wanx_v1
    llm_model: qwen_plus
    cfg:
        num_turns: 3
    params:
        style_name: "Storybook"

speech_generation:
    tool: speech_generation
    model: cosyvoice
    params:
        voice: "xiaoyun"
```

### 示例 2: 使用 OpenAI 模型

```yaml
models_config: configs/models.yaml

story_writer:
    tool: qa_outline_story_writer
    model: gpt_4o
    cfg:
        max_conv_turns: 3
    params:
        story_topic: "Adventure in the forest"

image_generation:
    tool: story_diffusion_t2i
    model: dalle_3
    llm_model: gpt_4o_mini
    cfg:
        num_turns: 2
    params:
        style_name: "Photographic"

speech_generation:
    tool: speech_generation
    model: kokoro
    params:
        voice: "af_heart"
```

### 示例 3: 混合使用不同提供商

```yaml
models_config: configs/models.yaml

story_writer:
    tool: qa_outline_story_writer
    model: gpt_4o  # 使用 OpenAI 生成故事
    cfg:
        max_conv_turns: 3

image_generation:
    tool: story_diffusion_t2i
    model: wanx_v1  # 使用 DashScope 生成图像
    llm_model: qwen_plus  # 使用 DashScope LLM 生成提示词

speech_generation:
    tool: speech_generation
    model: kokoro  # 使用本地 Kokoro TTS
```

## 添加新模型

### 1. 在 models.yaml 中添加模型定义

```yaml
llm_models:
  my_custom_llm:
    provider: openai  # 或其他provider
    model_name: my-model-name
    api_key_env: MY_API_KEY
    api_base_env: MY_API_BASE  # 可选
    default_params:
      temperature: 0.8
      max_tokens: 2000
```

### 2. 在 mm_story_agent.yaml 中使用

```yaml
story_writer:
    tool: qa_outline_story_writer
    model: my_custom_llm  # 使用新定义的模型
    cfg:
        max_conv_turns: 3
```

### 3. 设置环境变量

```bash
export MY_API_KEY="your-api-key"
export MY_API_BASE="https://your-api-endpoint.com/v1"
```

## 故障排除

### 问题: "Model 'xxx' not found"

**解决方案**: 
- 检查模型名称是否在 `models.yaml` 中正确定义
- 确保模型类型（llm/image/speech）与agent类型匹配

### 问题: "Environment variable XXX not set"

**解决方案**:
- 检查是否设置了相应的环境变量
- 确保环境变量名与 `models.yaml` 中的 `api_key_env` 字段一致

### 问题: API调用失败

**解决方案**:
- 验证API密钥是否正确
- 检查网络连接
- 查看API提供商的配额和限制

## 高级配置

### 自定义API端点

对于支持自定义端点的模型（如OpenAI兼容API）：

```yaml
llm_models:
  custom_openai:
    provider: openai
    model_name: gpt-3.5-turbo
    api_key_env: CUSTOM_API_KEY
    api_base_env: CUSTOM_API_BASE
    default_params:
      temperature: 0.7
```

```bash
export CUSTOM_API_KEY="your-key"
export CUSTOM_API_BASE="https://your-custom-endpoint.com/v1"
```

### 覆盖默认参数

在 `mm_story_agent.yaml` 中的 `cfg` 部分可以覆盖模型的默认参数：

```yaml
story_writer:
    tool: qa_outline_story_writer
    model: qwen2_72b
    cfg:
        temperature: 0.9  # 覆盖默认的 0.7
        max_tokens: 6000  # 覆盖默认的 4000
```

## 参考

- [DashScope API 文档](https://help.aliyun.com/zh/dashscope/)
- [OpenAI API 文档](https://platform.openai.com/docs/api-reference)
- [Stability AI API 文档](https://platform.stability.ai/docs/api-reference)
- [Replicate API 文档](https://replicate.com/docs)

