from __future__ import annotations

import asyncio
import logging

from api.apps import current_user, login_required
from api.db.joint_services.tenant_model_service import (
    get_tenant_default_model_by_type,
)
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.llm_service import LLMBundle
from api.utils.api_utils import (
    get_error_data_result,
    get_request_json,
    get_result,
)
from common import settings
from common.constants import LLMType


_vision_lock = asyncio.Lock()
_RETRY_MARKERS = ("429", "1302", "1305", "rate limit", "model busy")


@manager.route("/datasets/<dataset_id>/formula-vision", methods=["POST"])  # noqa: F821
@login_required
async def recognize_formula(dataset_id: str):
    """Read a stored formula crop with the tenant's configured vision model."""

    if not KnowledgebaseService.accessible(
        kb_id=dataset_id, user_id=current_user.id
    ):
        return get_error_data_result(message=f"You don't own the dataset {dataset_id}.")

    req = await get_request_json()
    image_id = str(req.get("image_id") or "").strip()
    prompt = str(req.get("prompt") or "").strip()
    if not image_id or not prompt:
        return get_error_data_result(message="`image_id` and `prompt` are required.")

    parts = image_id.split("-", 1)
    if len(parts) != 2 or parts[0] != dataset_id or not parts[1]:
        return get_error_data_result(message="The image does not belong to this dataset.")

    image = await asyncio.to_thread(settings.STORAGE_IMPL.get, parts[0], parts[1])
    if not image:
        return get_error_data_result(message="Formula image not found.")

    try:
        model_config = get_tenant_default_model_by_type(
            current_user.id, LLMType.IMAGE2TEXT
        )
        model = LLMBundle(current_user.id, model_config)
    except Exception as exc:
        logging.exception("Unable to initialize formula vision model")
        return get_error_data_result(message=str(exc))

    async with _vision_lock:
        last_error = ""
        for attempt in range(4):
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(model.describe_with_prompt, image, prompt),
                    timeout=120,
                )
                text = str(text or "").strip()
                if text and not any(
                    marker in text.lower() for marker in _RETRY_MARKERS
                ):
                    return get_result(
                        data={"text": text, "image_id": image_id, "attempt": attempt + 1}
                    )
                last_error = text or "Vision model returned an empty response."
            except Exception as exc:
                last_error = str(exc)
                if not any(
                    marker in last_error.lower() for marker in _RETRY_MARKERS
                ):
                    logging.exception("Formula vision request failed")
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)

    return get_error_data_result(message=last_error or "Formula vision failed.")
