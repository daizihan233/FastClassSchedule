from .ws import ConnectionManager

websocket_clients: dict[tuple[str, int], ConnectionManager] = {}
