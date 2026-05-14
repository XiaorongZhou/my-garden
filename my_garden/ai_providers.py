from __future__ import annotations

import base64
import json
import mimetypes
import re
import sys
from dataclasses import dataclass
from urllib import error as urllib_error
from urllib import request as urllib_request

from .config import (
    AI_PROVIDER,
    AI_TIMEOUT_SECONDS,
    LOCAL_VLM_API_KEY,
    LOCAL_VLM_BASE_URL,
    LOCAL_VLM_MODEL,
    MODEL_DEBUG,
    OPENAI_PLANT_MODEL,
    OPENAI_RESPONSES_URL,
)


@dataclass(frozen=True)
class ModelImage:
    filename: str
    content_type: str
    photo_bytes: bytes
    detail: str = "high"


def openai_api_key() -> str:
    import os

    return os.environ.get("OPENAI_API_KEY", "").strip()


def active_provider_source() -> str:
    provider = (AI_PROVIDER or "openai").strip().lower()
    if provider in {"local", "qwen", "vllm", "openai-compatible"}:
        return "local"
    return "openai"


def model_runtime_summary() -> str:
    source = active_provider_source()
    if source == "local":
        return (
            "AI runtime: "
            f"provider={AI_PROVIDER or 'local'} "
            f"source=local "
            f"model={LOCAL_VLM_MODEL or 'unset'} "
            f"base_url={LOCAL_VLM_BASE_URL or 'unset'} "
            f"api_key={'set' if bool(LOCAL_VLM_API_KEY) else 'missing'} "
            f"debug={'on' if MODEL_DEBUG else 'off'}"
        )
    return (
        "AI runtime: "
        f"provider={AI_PROVIDER or 'openai'} "
        f"source=openai "
        f"model={OPENAI_PLANT_MODEL or 'unset'} "
        f"url={OPENAI_RESPONSES_URL or 'unset'} "
        f"api_key={'set' if bool(openai_api_key()) else 'missing'} "
        f"debug={'on' if MODEL_DEBUG else 'off'}"
    )


def log_model_event(event: str, **fields: object) -> None:
    if not MODEL_DEBUG:
        return
    rendered_fields = " ".join(
        f"{key}={str(value).replace(chr(10), ' ') or 'empty'}"
        for key, value in fields.items()
    )
    message = f"[model] {event}"
    if rendered_fields:
        message = f"{message} {rendered_fields}"
    print(message, file=sys.stderr, flush=True)


def live_model_available() -> bool:
    if active_provider_source() == "local":
        return bool(LOCAL_VLM_BASE_URL.strip() and LOCAL_VLM_MODEL.strip())
    return bool(openai_api_key())


def image_data_url(*, image_bytes: bytes, filename: str = "", content_type: str = "") -> str:
    guessed_type = content_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{guessed_type};base64,{encoded}"


def _post_json(
    *,
    url: str,
    payload: dict[str, object],
    timeout_seconds: float,
    api_key: str = "",
) -> dict[str, object]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Model request failed ({exc.code}). {raw_error[:320]}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Model request failed. {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Model request timed out.") from exc
    except OSError as exc:
        raise RuntimeError(f"Model request failed. {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON. {exc}") from exc
    if not isinstance(response_payload, dict):
        raise RuntimeError("Model response was not a JSON object.")
    return response_payload


def _extract_openai_output_text(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = payload.get("output")
    if not isinstance(output_items, list):
        raise RuntimeError("OpenAI response did not include output text.")

    text_chunks: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in {"output_text", "text"}:
                continue
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_chunks.append(text_value)

    if not text_chunks:
        raise RuntimeError("OpenAI response did not include parsable text content.")
    return "\n".join(text_chunks)


def _extract_chat_completion_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Chat completion response did not include choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("Chat completion response choice was malformed.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Chat completion response did not include a message.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        text_chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"text", "output_text"}:
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_chunks.append(text_value)
        if text_chunks:
            return "\n".join(text_chunks)
    raise RuntimeError("Chat completion response did not include text content.")


def _extract_json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not match:
        raise RuntimeError("Model returned non-JSON output.")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON content. {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Model output was not a JSON object.")
    return parsed


def _local_chat_completions_url() -> str:
    base = LOCAL_VLM_BASE_URL.strip().rstrip("/")
    if not base:
        raise RuntimeError("LOCAL_VLM_BASE_URL is not configured.")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def call_structured_output(
    *,
    schema_name: str,
    schema: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    image: ModelImage | None = None,
) -> dict[str, object]:
    if active_provider_source() == "local":
        return _call_local_structured_output(
            schema_name=schema_name,
            schema=schema,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image=image,
        )
    return _call_openai_structured_output(
        schema_name=schema_name,
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        image=image,
    )


def _call_openai_structured_output(
    *,
    schema_name: str,
    schema: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    image: ModelImage | None = None,
) -> dict[str, object]:
    api_key = openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    log_model_event(
        "request",
        provider="openai",
        model=OPENAI_PLANT_MODEL,
        endpoint=OPENAI_RESPONSES_URL,
        schema=schema_name,
        image="yes" if image else "no",
    )

    user_content: list[dict[str, object]] = [{"type": "input_text", "text": user_prompt}]
    if image:
        user_content.append(
            {
                "type": "input_image",
                "image_url": image_data_url(
                    image_bytes=image.photo_bytes,
                    filename=image.filename,
                    content_type=image.content_type,
                ),
                "detail": image.detail,
            }
        )

    payload = {
        "model": OPENAI_PLANT_MODEL,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }

    response_payload = _post_json(
        url=OPENAI_RESPONSES_URL,
        payload=payload,
        timeout_seconds=AI_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    raw_text = _extract_openai_output_text(response_payload)
    parsed = _extract_json_object(raw_text)
    log_model_event(
        "response",
        provider="openai",
        model=OPENAI_PLANT_MODEL,
        schema=schema_name,
    )
    return parsed


def _call_local_structured_output(
    *,
    schema_name: str,
    schema: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    image: ModelImage | None = None,
) -> dict[str, object]:
    user_content: list[dict[str, object]] = [{"type": "text", "text": user_prompt}]
    if image:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url(
                        image_bytes=image.photo_bytes,
                        filename=image.filename,
                        content_type=image.content_type,
                    )
                },
            }
        )

    base_payload = {
        "model": LOCAL_VLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    api_key = LOCAL_VLM_API_KEY
    endpoint = _local_chat_completions_url()
    log_model_event(
        "request",
        provider=AI_PROVIDER or "local",
        source="local",
        model=LOCAL_VLM_MODEL,
        endpoint=endpoint,
        schema=schema_name,
        image="yes" if image else "no",
        api_key="set" if bool(api_key) else "missing",
    )
    try:
        response_payload = _post_json(
            url=endpoint,
            payload={
                **base_payload,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    },
                },
            },
            timeout_seconds=AI_TIMEOUT_SECONDS,
            api_key=api_key,
        )
        raw_text = _extract_chat_completion_text(response_payload)
        parsed = _extract_json_object(raw_text)
        log_model_event(
            "response",
            provider=AI_PROVIDER or "local",
            source="local",
            model=LOCAL_VLM_MODEL,
            schema=schema_name,
            mode="json_schema",
        )
        return parsed
    except RuntimeError as first_error:
        log_model_event(
            "retry",
            provider=AI_PROVIDER or "local",
            source="local",
            model=LOCAL_VLM_MODEL,
            schema=schema_name,
            reason=str(first_error)[:220],
        )
        fallback_prompt = (
            f"{user_prompt}\n\n"
            "Return only one JSON object that matches this schema exactly:\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        fallback_payload = {
            **base_payload,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": fallback_prompt},
                        *user_content[1:],
                    ],
                },
            ],
        }
        try:
            response_payload = _post_json(
                url=endpoint,
                payload=fallback_payload,
                timeout_seconds=AI_TIMEOUT_SECONDS,
                api_key=api_key,
            )
            raw_text = _extract_chat_completion_text(response_payload)
            parsed = _extract_json_object(raw_text)
            log_model_event(
                "response",
                provider=AI_PROVIDER or "local",
                source="local",
                model=LOCAL_VLM_MODEL,
                schema=schema_name,
                mode="prompt_schema",
            )
            return parsed
        except RuntimeError as second_error:
            log_model_event(
                "failure",
                provider=AI_PROVIDER or "local",
                source="local",
                model=LOCAL_VLM_MODEL,
                schema=schema_name,
                reason=str(second_error)[:220],
            )
            raise RuntimeError(f"{first_error} Fallback parse also failed. {second_error}") from second_error
