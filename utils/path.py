import asyncio
import pathlib


def _discovery_path(path, directory=True, file=False, depth=1) -> list[str]:
    root = pathlib.Path(path)
    lst = root.glob('/'.join(["*"] * depth))
    if directory and file:
        return [str(p.relative_to(root)) for p in lst]
    elif directory:
        return [str(p.relative_to(root)) for p in lst if p.is_dir()]
    elif file:
        return [str(p.relative_to(root)) for p in lst if p.is_file()]
    else:
        return []  # But why?

async def discovery_path(path, directory=True, file=False, depth=1) -> list[str]:
    """
    发现目录
    :param path:
    :param directory: 是否列出目录
    :param file: 是否列出文件
    :param depth: 深度
    :return: 一个列表，包含目录中的所有文件或文件夹的相对路径（不以 ./ 开头）
    """
    return await asyncio.to_thread(_discovery_path, path, directory=directory, file=file, depth=depth)
