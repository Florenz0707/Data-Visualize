import os
from pathlib import Path

def load_env(env_path: Path = Path("configs/.env")):
    """
    从 .env 文件加载环境变量。

    Args:
        env_path (Path): .env 文件的路径。
    """
    if not env_path.exists():
        # 如果 .env 文件不存在，则静默失败，依赖于已设置的环境变量
        return

    print(f"✓ Loading environment variables from {env_path}")
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 分割键值对
                if '=' not in line:
                    continue
                
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # 去除值的引号（单引号或双引号）
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                
                # 如果环境变量未设置，则设置它
                if key not in os.environ:
                    os.environ[key] = value
                    # print(f"  - Setting env var: {key}") # 取消注释以进行调试
                # else:
                    # print(f"  - Env var '{key}' already set, skipping.") # 取消注释以进行调试
    except Exception as e:
        print(f"✗ Error loading .env file: {e}")

