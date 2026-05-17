class GovernanceConfig(ImmutableRecord):
    bursar: MachineID = "unlimited"
    sentinel: MachineID = "passthrough"
    human_gate: MachineID = "auto_approve"

class AgentBlueprint(ImmutableRecord):
    # 1. Identidad
    id: MachineID
    name: DisplayName
    
    # 2. Cognición
    model: ModelSpec # (Con el validador Pydantic para admitir "google/gemini-2.5-flash")
    system_prompt: SemanticText # (Aquí vive Jinja2)
    
    # 3. Interfaces (El cambio fuerte)
    triggers: list[str] = Field(default_factory=list) # Canales de EventBus que escucha
    tools: list[AgentToolConfig] = Field(default_factory=list) # Herramientas/Sub-agentes
    
    # 4. Ciclo de vida y Gobernanza
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)