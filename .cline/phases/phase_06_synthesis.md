# Phase 0.6: Synthesis Engine & Critic Loop

## Objective
Generate complete, on-style short-form video screenplays matching the creator's persona using swappable LLM providers, verified by an automated critic loop.

## Scope of Work
1. **LLM Provider Integration (`app/capabilities/llm/`)**:
   - Support Anthropic Claude, OpenAI GPT, Google Gemini, and local Ollama.
2. **Beat Planner (`app/synthesis/beat_planner.py`)**:
   - Plan narrative beats (Hook, Setup, Escalation, Punchline/Value, CTA) mapped to strict target timing windows based on persona ASD.
3. **Screenplay Writer (`app/synthesis/screenplay_writer.py`)**:
   - Produce two-column AV scripts: Audio (spoken words, pacing, sound effects) + Visual (shot type, action, b-roll, text overlays).
4. **Automated Critic (`app/synthesis/critic.py`)**:
   - Deterministic checks: Target duration vs projected WPM, hook length, Hinglish tone match.
   - Optional LLM-as-a-judge reflection loop to revise script if critic criteria fail.

## Acceptance Criteria
- [ ] `generate_script.py --creator <id> --topic <topic>` outputs an AV screenplay adhering to the creator's pacing and stylistic traits.
- [ ] Scripts failing critic checks automatically undergo revision cycles before export.