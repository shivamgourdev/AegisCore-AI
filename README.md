# AegisCore AI

Production-grade RAG + email drafting assistant with local LLM (Ollama),
Graph RAG (NetworkX + SQLite), hybrid retrieval (ChromaDB + BM25),
citation verification, abstention gate, and Gmail OAuth2 draft approval.

## Hardware baseline (dev)
Intel Core i3-1215U, ~8 GB RAM, Intel UHD, no NVIDIA GPU, Windows 11.

## Resource rules (enforced)
- Only one heavy model at a time (LLM and vision mutually exclusive)
- Max 1 concurrent inference request; batch size = 1
- Vision runs via cloud path (local vision does not fit alongside Docker + DBs)

## Status
DRAFT — pre-implementation. Nothing verified until code runs.

See `plan.md` for the full implementation plan (20 phases).
