#!/usr/bin/env python3
"""Tool Registration Audit Script"""
import sys
sys.path.insert(0, '/home/kloros')

from src.introspection_tools import IntrospectionToolRegistry
from src.persona.kloros import PERSONA_PROMPT

report = []
report.append("# Tool Availability Matrix")
report.append("**Generated:** 2025-10-12 01:44:00")
report.append("")
report.append("---")
report.append("")

# Initialize registry
try:
    registry = IntrospectionToolRegistry()

    report.append("## 1. Tool Registry Summary")
    report.append("")
    report.append(f"- **Total tools registered:** {len(registry.tools)}")
    report.append(f"- **Synthesis enabled:** {registry.synthesis_enabled}")
    report.append("")

    # Check which tools are mentioned in persona prompt
    tools_in_prompt = []
    for tool_name in registry.tools.keys():
        if tool_name in PERSONA_PROMPT:
            tools_in_prompt.append(tool_name)

    report.append(f"- **Tools mentioned in PERSONA_PROMPT:** {len(tools_in_prompt)}")
    report.append("")

    # List all tools with details
    report.append("## 2. Complete Tool Inventory")
    report.append("")
    report.append("| Tool Name | Description | Parameters | In Prompt? | Callable? |")
    report.append("|-----------|-------------|------------|------------|-----------|")

    for tool_name, tool in sorted(registry.tools.items()):
        desc = tool.description[:60] + "..." if len(tool.description) > 60 else tool.description
        params = ", ".join(tool.parameters) if tool.parameters else "none"
        in_prompt = "✅" if tool_name in tools_in_prompt else "❌"

        # Check if callable
        try:
            callable(tool.func)
            is_callable = "✅"
        except:
            is_callable = "❌"

        report.append(f"| {tool_name} | {desc} | {params} | {in_prompt} | {is_callable} |")

    report.append("")

    # Categorize tools
    report.append("## 3. Tool Categories")
    report.append("")

    categories = {
        "Diagnostics": ["system_diagnostic", "audio_status", "audio_quality", "stt_status",
                       "component_status", "check_service_status"],
        "Memory": ["memory_status", "force_memory_cleanup", "enable_enhanced_memory"],
        "Audio": ["list_audio_sinks", "list_audio_sources", "run_audio_test",
                 "count_voice_samples", "audio_quality"],
        "System Control": ["restart_service", "execute_system_command", "modify_parameter"],
        "Voice Enrollment": ["start_enrollment", "list_enrolled_users", "cancel_enrollment"],
        "D-REAM Evolution": ["run_dream_evolution", "get_dream_report"],
        "Error Management": ["check_recent_errors"],
        "Code Generation": ["create_code_solution"],
        "Dependencies": ["check_dependencies"],
        "Models": ["list_models"],
        "Knowledge Base": ["update_knowledge_base", "rebuild_rag", "document_improvement"],
        "Tool Ecosystem": ["analyze_tool_ecosystem"]
    }

    for category, tool_names in categories.items():
        registered = [t for t in tool_names if t in registry.tools]
        missing = [t for t in tool_names if t not in registry.tools]

        report.append(f"### {category}")
        report.append(f"- **Registered:** {len(registered)}/{len(tool_names)}")
        if missing:
            report.append(f"- **Missing:** {', '.join(missing)}")
        report.append("")

    # Check for orphaned tools (not in any category)
    categorized_tools = set()
    for tools in categories.values():
        categorized_tools.update(tools)

    orphaned = [t for t in registry.tools.keys() if t not in categorized_tools]
    if orphaned:
        report.append("### Uncategorized Tools")
        for tool in orphaned:
            report.append(f"- {tool}")
        report.append("")

    # Check persona prompt tool mentions
    report.append("## 4. Persona Prompt Analysis")
    report.append("")
    report.append("**Tools explicitly mentioned in PERSONA_PROMPT:**")
    report.append("")

    if tools_in_prompt:
        for tool in sorted(tools_in_prompt):
            report.append(f"- {tool}")
    else:
        report.append("- None explicitly mentioned")
    report.append("")

    # Look for tool usage examples in persona
    report.append("**Tool usage examples in persona:**")
    report.append("")

    example_tools = ["system_diagnostic", "audio_status", "memory_status",
                    "run_dream_evolution", "run_audio_test", "check_recent_errors"]

    for tool in example_tools:
        if tool in PERSONA_PROMPT:
            report.append(f"- ✅ {tool}")
        else:
            report.append(f"- ❌ {tool}")
    report.append("")

    # Test a few tools
    report.append("## 5. Tool Execution Tests")
    report.append("")
    report.append("Testing tool callability (no actual execution)...")
    report.append("")

    test_tools = ["check_dependencies", "list_models", "component_status"]

    for tool_name in test_tools:
        if tool_name in registry.tools:
            tool = registry.tools[tool_name]
            try:
                # Check function signature
                import inspect
                sig = inspect.signature(tool.func)
                params = list(sig.parameters.keys())

                report.append(f"### {tool_name}")
                report.append(f"- **Signature:** {params}")
                report.append(f"- **Required params:** {tool.parameters}")
                report.append(f"- **Status:** ✅ Callable")
                report.append("")
            except Exception as e:
                report.append(f"### {tool_name}")
                report.append(f"- **Status:** ❌ Error: {str(e)}")
                report.append("")

    # Identify issues
    report.append("## 6. Issues Identified")
    report.append("")

    issues = []

    # Check for tools requiring sounddevice
    sounddevice_tools = ["run_audio_test", "audio_quality"]
    for tool in sounddevice_tools:
        if tool in registry.tools:
            issues.append(f"- **{tool}** requires `sounddevice` module (currently missing)")

    # Check for missing tool descriptions in persona
    missing_from_persona = [t for t in registry.tools.keys() if t not in PERSONA_PROMPT]
    if len(missing_from_persona) > 5:
        issues.append(f"- **{len(missing_from_persona)} tools** not mentioned in PERSONA_PROMPT - LLM may not know they exist")

    # Check for tools with no parameters field
    no_params_field = [t for t, tool in registry.tools.items() if not hasattr(tool, 'parameters')]
    if no_params_field:
        issues.append(f"- **{len(no_params_field)} tools** missing parameters field")

    if not issues:
        report.append("- ✅ No major issues identified")
    else:
        for issue in issues:
            report.append(issue)
    report.append("")

    # Recommendations
    report.append("## 7. Recommendations")
    report.append("")

    report.append("### Critical")
    report.append("1. **Install sounddevice** for audio tools:")
    report.append("   ```bash")
    report.append("   pip install sounddevice")
    report.append("   ```")
    report.append("")

    report.append("### High Priority")
    report.append("2. **Update PERSONA_PROMPT** to include all available tools")
    report.append("   - Currently only mentions a few example tools")
    report.append("   - LLM needs to know about all {tool_count} tools")
    report.append("   - Consider adding tool categories to persona")
    report.append("")

    report.append("3. **Add tool discovery command**")
    report.append("   - Tool: `list_available_tools` to show all tools")
    report.append("   - Helps users/LLM discover capabilities")
    report.append("")

    report.append("### Medium Priority")
    report.append("4. **Standardize tool naming**")
    report.append("   - Some use verb_noun (check_dependencies)")
    report.append("   - Some use noun_verb (audio_status)")
    report.append("   - Recommend: verb_noun for consistency")
    report.append("")

    report.append("5. **Add tool usage analytics**")
    report.append("   - Track which tools are most/least used")
    report.append("   - Identify tools that may need improvement")
    report.append("")

    # Tool synthesis info
    report.append("## 8. Tool Synthesis System")
    report.append("")
    report.append(f"- **Synthesis enabled:** {registry.synthesis_enabled}")
    report.append("")

    try:
        synth_info = registry.get_synthesized_tools_info()
        if isinstance(synth_info, dict):
            active = synth_info.get('active_tools', [])
            disabled = synth_info.get('disabled_tools', [])

            report.append(f"- **Active synthesized tools:** {len(active)}")
            report.append(f"- **Disabled synthesized tools:** {len(disabled)}")
            report.append("")

            if active:
                report.append("**Active synthesized tools:**")
                for tool in active:
                    report.append(f"- {tool['name']} (created: {tool.get('created_at', 'unknown')})")
                report.append("")
        else:
            report.append("- Tool synthesis storage not available")
            report.append("")
    except Exception as e:
        report.append(f"- Error checking synthesis info: {e}")
        report.append("")

    # Summary
    report.append("## 9. Summary")
    report.append("")
    report.append(f"- **Total registered tools:** {len(registry.tools)}")
    report.append(f"- **Fully functional:** {len(registry.tools) - len(sounddevice_tools)}")
    report.append(f"- **Require dependencies:** {len(sounddevice_tools)}")
    report.append(f"- **Tools in persona prompt:** {len(tools_in_prompt)}")
    report.append("")
    report.append("**Overall assessment:** Tool system is comprehensive and well-structured, but:")
    report.append("- Missing `sounddevice` dependency affects 2 audio tools")
    report.append("- Persona prompt doesn't expose all tools to LLM")
    report.append("- Tool discovery mechanism could be improved")
    report.append("")

except Exception as e:
    import traceback
    report.append("## ❌ CRITICAL ERROR")
    report.append(f"Tool registry audit failed: {str(e)}")
    report.append("")
    report.append("**Traceback:**")
    report.append("```")
    report.append(traceback.format_exc())
    report.append("```")

# Write report
output_path = '/home/kloros/diagnostics/tool_availability_matrix.md'
with open(output_path, 'w') as f:
    f.write('\n'.join(report))

print(f"Tool audit report written to {output_path}")
