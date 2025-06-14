from backend.llamastack import LLAMASTACK_URL
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from llama_stack_client import LlamaStackClient
from llama_stack_client.types import UserMessage, SystemMessage, CompletionMessage
from typing import List, Dict, Any, AsyncGenerator, Literal
import logging
from pydantic import BaseModel

class Message(BaseModel):
    role: Literal['user', 'assistant', 'system']
    content: str

log = logging.getLogger(__name__)

router = APIRouter(prefix="/llama_stack", tags=["llama_stack"])

# Initialize LlamaStack client
client = LlamaStackClient(base_url=LLAMASTACK_URL)

@router.get("/llms", response_model=List[Dict[str, Any]])
async def get_llms():
    """Get available LLMs from LlamaStack"""
    try:
        log.info(f"Attempting to fetch models from LlamaStack at {client.base_url}")
        try:
            models = client.models.list()
            log.info(f"Received response from LlamaStack: {models}")
        except Exception as client_error:
            log.error(f"Error calling LlamaStack API: {str(client_error)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to connect to LlamaStack API: {str(client_error)}"
            )

        if not models:
            log.warning("No models returned from LlamaStack")
            return []

        llms = []
        for model in models:
            try:
                if model.model_type == "llm":
                    llm_config = {
                        "id": str(model.identifier),
                        "name": model.provider_resource_id,
                        "model_type": model.model_type,
                    }
                    llms.append(llm_config)
            except AttributeError as ae:
                log.error(f"Error processing model data: {str(ae)}. Model data: {model}")
                continue

        log.info(f"Successfully processed {len(llms)} LLM models")
        return llms

    except Exception as e:
        log.error(f"Unexpected error in get_llms: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/knowledge_bases", response_model=List[Dict[str, Any]])
async def get_knowledge_bases():
    """Get available knowledge bases from LlamaStack"""
    try:
        kbs = client.vector_dbs.list()
        return [{
            "id": str(kb.id),
            "name": kb.name,
            "version": kb.version,
        } for kb in kbs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mcp_servers", response_model=List[Dict[str, Any]])
async def get_mcp_servers():
    """Get available MCP servers from LlamaStack"""
    try:
        servers = client.toolgroups.list()
        return [{
            "id": str(server.identifier),
            "name": server.provider_resource_id,
            "title": server.provider_id,
        } for server in servers]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/safety_models", response_model=List[Dict[str, Any]])
async def get_safety_models():
    """Get available safety models from LlamaStack"""
    try:
        models = client.models.list()
        safety_models = []
        for model in models:
            if model.model_type == "safety":
                safety_model = {
                    "id": str(model.identifier),
                    "name": model.provider_resource_id,
                    "model_type": model.type,
                }
                safety_models.append(safety_model)
        return safety_models
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/embedding_models", response_model=List[Dict[str, Any]])
async def get_embedding_models():
    """Get available embedding models from LlamaStack"""
    try:
        models = client.models.list()
        embedding_models = []
        for model in models:
            if model.model_type == "embedding":
                embedding_model = {
                    "id": str(model.identifier),
                    "name": model.provider_resource_id,
                    "model_type": model.type,
                }
                embedding_models.append(embedding_model)
        return embedding_models
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shields", response_model=List[Dict[str, Any]])
async def get_shields():
    """Get available shields from LlamaStack"""
    try:
        shields = client.shields.list()
        shields_list = []
        for shield in shields:
            shield = {
                    "id": str(shield.identifier),
                    "name": shield.provider_resource_id,
                    "model_type": shield.type,
                }
            shields_list.append(shield)
        return shields_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False

@router.post("/chat")
def chat(request: ChatRequest):
    """Chat endpoint that streams responses from LlamaStack"""
    try:
        log.info(f"Received request: {request.dict()}")
        # Get the list of available LLM model
        models = client.models.list()
        llm_model = None
        
        # If the requested model is available, use it
        for model in models:
            if model.model_type == "llm":
                if model.identifier == request.model:
                    llm_model = model
                    break

        if not llm_model:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No LLM model available"
            )

        # Convert Message objects to appropriate LlamaStack message types
        log.info(f"Processing messages: {request.messages}")
        llama_messages = []
        for msg in request.messages:
            if msg.role == 'user':
                llama_messages.append(UserMessage(role=msg.role, content=msg.content))
            elif msg.role == 'assistant':
                llama_messages.append(CompletionMessage(role=msg.role, content=msg.content, stop_reason='end_of_turn'))
            elif msg.role == 'system':
                llama_messages.append(SystemMessage(role=msg.role, content=msg.content))
        
        log.info(f"Using model: {llm_model.identifier}")
        log.info(f"Sending messages: {llama_messages}")
        
        def generate_response() -> AsyncGenerator[str, None]:
            try:
                # Get the response stream from LlamaStack
                response = client.inference.chat_completion(
                    model_id=llm_model.identifier,
                    messages=llama_messages,
                    stream=True
                )
                # Stream each chunk as it arrives
                log.info("Starting to stream response")
                for chunk in response:
                    if chunk and chunk.event and chunk.event.delta and chunk.event.delta.text:
                        log.info(f"Sending chunk: {chunk.event.delta.text}")
                        yield f"data: {chunk.event.delta.text}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                log.error(f"Error in stream: {str(e)}")
                yield f"data: Error: {str(e)}\n\n"

        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream"
        )

    except Exception as e:
        log.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
