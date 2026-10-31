# Car Manual Explorer

## Context-Aware Intelligent Retrieval for Technical Docs

![MongoDB](https://img.shields.io/badge/MongoDB-%234ea94b.svg?style=for-the-badge&logo=mongodb&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Next JS](https://img.shields.io/badge/Next-black?style=for-the-badge&logo=next.js&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Google Cloud](https://img.shields.io/badge/GoogleCloud-%234285F4.svg?style=for-the-badge&logo=google-cloud&logoColor=white)

**Intelligent search and retrieval for automotive technical documentation.**

This platform demonstrates MongoDB's Unified Data Platform capabilities, showcasing how flexible JSON document storage enables multiple retrieval pipelines working together: smart chunking, full-text search, vector embeddings, knowledge graphs, multimodal search, and Voyage AI reranking.

By the end of this guide you'll have a comprehensive car manual exploration system up and running, capable of all the solutions mentioned above.

### What This App Does

Car Manual Explorer is an intelligent search & retrieval system designed to help technicians, mechanics, and automotive professionals quickly find relevant information across complex technical documentation. The application solves the common problem of navigating lengthy, multi-section car manuals by providing five distinct retrieval methods, each optimized for different types of queries and use cases.

**Key Capabilities:**

- **Five Retrieval Techniques**: Vector Search (semantic similarity), Text Search (keyword-based), Hybrid Search (combined vector + text), GraphRAG Search (relationship-aware), and Multimodal Search (text + images)
- **Optional AI Reranking**: Voyage AI reranker improves result relevance across all search methods
- **Multimodal Support**: Search both text content and images using natural language queries or image uploads
- **Context-Aware Results**: Preserves hierarchical structure and relationships between document sections

**Value Proposition:**

- Reduces search time by 60-75% compared to manual document navigation
- Improves accuracy with intelligent semantic understanding
- Enables multimodal discovery (find images by describing them in text)
- Provides relationship-aware search through knowledge graph traversal

**Use Cases:**

- Finding specific repair procedures ("How do I change a tire?")
- Troubleshooting issues ("What causes engine overheating?")
- Understanding component relationships ("What systems are related to the brake system?")
- Locating visual references ("Show me the engine diagram")
- Discovering related procedures through graph traversal

We will walk you through the process of configuring and using [MongoDB Atlas](https://www.mongodb.com/atlas) as your backend with [Google Vertex AI](https://cloud.google.com/vertex-ai) for MongoDB-powered search and question answering in your [Next.js](https://nextjs.org/) and [FastAPI](https://fastapi.tiangolo.com/) application.

The architecture we're about to set up is depicted in the diagram below:

![Car Manual Explorer Architecture](frontend/public/architecture-diagram.png)

**Key Platform Capabilities:**

The application provides five distinct retrieval techniques, each optimized for different query types:

1. **Vector Search**: Semantic similarity using AI embeddings (768-dim vectors) - finds conceptually similar content even without keyword matches
2. **Text Search**: Keyword-based search with fuzzy matching and stemming - advanced compound query structure prioritizes exact phrases, individual words, and handles typos
3. **Hybrid Search**: Combines vector + text using MongoDB's native `$rankFusion` - Reciprocal Rank Fusion (RRF) with intelligent score weighting
4. **GraphRAG Search**: Relationship-aware search using MongoDB's `$graphLookup` for knowledge graph traversal - expands results through document relationships
5. **Multimodal Search**: Text-to-image and image-to-image search using Voyage AI multimodal embeddings (1024-dim) - search images using text queries or find similar images

**Optional Enhancement:**

- **Voyage AI Reranker**: Optional AI-powered reranking that improves result relevance across all search methods using cross-encoder technology (rerank-2.5 model)

**Additional Capabilities:**

- **Unified Data Platform**: MongoDB's flexible JSON document model serves as the foundation for both storage and retrieval
- **Context-Aware Chunking**: Smart document processing that preserves hierarchical structure and relationships
