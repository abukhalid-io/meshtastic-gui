"""Small shared helpers."""
import time


def proto_to_dict(obj):
    """Best-effort conversion of a protobuf message (or plain dict/value) into
    a plain Python dict/value, so the UI can render arbitrary device info
    without depending on exact meshtastic-python protobuf field names."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    try:
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(obj, preserving_proto_field_name=True)
    except Exception:  # noqa: BLE001 - not a protobuf message, or conversion failed
        return {"value": str(obj)}


def flatten(d, prefix=""):
    """Flatten a nested dict into a list of (key, value) pairs for simple
    key/value table display."""
    out = []
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.extend(flatten(v, prefix=f"{key}."))
        else:
            out.append((key, v))
    return out


def fmt_timestamp(ts):
    if not ts:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:  # noqa: BLE001
        return str(ts)


def node_display_id(node):
    user = node.get("user", {}) if isinstance(node, dict) else {}
    return user.get("id") or f"!{node.get('num', 0):08x}"
