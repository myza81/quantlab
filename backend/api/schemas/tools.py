from pydantic import BaseModel


class ToolParameterResponse(BaseModel):
    name: str
    type_label: str
    required: bool
    default: object | None = None
    min_value: float | None = None
    max_value: float | None = None


class ToolMetadataResponse(BaseModel):
    tool_id: str
    name: str
    short_name: str | None = None
    version: str
    category: str
    status: str
    description: str
    input_data_family: str
    output_feature_names: list[str]
    parameters: list[ToolParameterResponse]
    supported_runtime_modes: list[str]
    visualization_capabilities: list[str]
    min_warmup_bars: int
    stateful: bool


class ToolListResponse(BaseModel):
    tools: list[ToolMetadataResponse]


class ToolSetValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
