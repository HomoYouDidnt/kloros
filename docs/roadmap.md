# KLoROS Development Roadmap

**Last Updated:** 2025-11-26

This is a living document that tracks the development roadmap for KLoROS (Knowledge-based Logic & Reasoning Operating System). It outlines the phased approach to system cleanup, infrastructure improvements, feature rebuilds, and future research directions. This document will be updated as tasks are completed and new priorities emerge.

---

## PHASE 1: CLEANUP (Clear the Decks)

- [ ] Decompose housekeeping.py monolith (1697 lines) into agentic services
- [ ] Strip Dashboard V1, rename V2 to just "Dashboard"
- [ ] Strip text-only chat function (will reimplement with new build later)
- [ ] Strip alert function (will reimplement with new build later)
- [ ] Strip user recognition & registration (will reimplement with new build later)
- [ ] Remove redundant routing services (UMN handles routing implicitly via topic structure)
- [ ] Directory rebuild / reorganization

## PHASE 2: INFRASTRUCTURE

- [ ] Migration to llama.cpp (audit Ollama conveniences, rebuild as native KLoROS functions if needed)
- [ ] Determine system bring-up order for testing
- [ ] Domain reorganization (Voice ✓ completed, identify other domains)

## PHASE 3: REBUILD (On Clean Foundation)

- [ ] Text-only chat using same backend as voice (conversations at correct engagement level)
- [ ] Integrate text-only chat to new Dashboard
- [ ] Dashboard: Realtime system journal with selectable variables for specific outputs
- [ ] Dashboard: Interactive emergency buttons (lockdown, maintenance mode, lobotomy)
- [ ] Persona prompt adjustment (sarcasm, sardonic wit, dry humor, affectionate roasting while maintaining helpfulness)

## PHASE 4: RESEARCH & FUTURE

- [ ] Observer for proactive methodology capture (watches Claude Code work, watches LLM reasoning, trains private LLM in background)
- [ ] Local LLM that learns from observing other LLMs and services (Fara-7B, SAM 3, Power BI MCP)
- [ ] Examine Nemotron Elastic as potential implementation (or how it adapts)
- [ ] Examine Agent SOPs for training SPICA cells into agents
- [ ] Figure out nested learning architecture for KLoROS
- [ ] Develop roadmap and goal achievement points for KLoROS before refactoring D-REAM

---

## COMPLETED

- [x] LocalRagBackend elimination (1531 lines) - 2025-11-26
- [x] Voice domain reorganization - 2025-11-26
- [x] cognitive_actions_subscriber.py elimination - 2025-11-26
- [x] Voice Services Refactor - 2025-11-25
- [x] Tool System Removal - 2025-11-24
