"""Metadata-only formatter: never interpolate messages, args or exceptions."""
import json
import logging


class MetadataFormatter(logging.Formatter):
    def format(self, record):
        event = {"event": "runtime", "level": record.levelname,
                 "source": record.name, "line": record.lineno}
        if record.name == "uvicorn.access":
            event["event"] = "http_request"
            # Uvicorn: client, method, path (with query), HTTP version, status.
            if isinstance(record.args, tuple) and len(record.args) == 5:
                _, method, path, _, status = record.args
                route = str(path).split("?", 1)[0]
                event.update(
                    method=method if method in {"GET", "POST", "HEAD", "OPTIONS"} else "other",
                    route=route if route in {"/health", "/v1/models", "/v1/chat/completions",
                                            "/v1/completions", "/metrics"} else "other",
                    status=int(status),
                )
        return json.dumps(event, ensure_ascii=True)
