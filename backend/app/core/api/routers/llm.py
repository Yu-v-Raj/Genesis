"""Minimal REST adapters for LLM Runtime integration verification."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.api.dependencies.system import get_llm_manager
from backend.app.core.api.schemas.llm import GenerateRequest, GenerateResponse, ModelListResponse, ModelResponse, ProviderListResponse
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError, LLMProviderError, LLMRuntimeError, LLMTimeoutError, ProviderNotFoundError, ProviderUnavailableError


router = APIRouter(prefix="/api/llm", tags=["llm"])
Manager = Annotated[LLMManager, Depends(get_llm_manager)]


@router.get("/providers", response_model=ProviderListResponse)
def providers(manager: Manager) -> ProviderListResponse:
    return ProviderListResponse(providers=list(manager.providers()))


@router.get("/models", response_model=ModelListResponse)
def models(manager: Manager) -> ModelListResponse:
    return ModelListResponse(models=[ModelResponse.from_domain(model) for model in manager.models()])


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, manager: Manager) -> GenerateResponse:
    try:
        return GenerateResponse.from_domain(await manager.generate(request.to_domain()))
    except ProviderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (LLMConfigurationError, ProviderUnavailableError) as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except LLMTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(error)) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (LLMRuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
