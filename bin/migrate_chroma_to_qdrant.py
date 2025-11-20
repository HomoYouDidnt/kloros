#!/usr/bin/env python3
"""
ChromaDB → Qdrant Migration Script

Safely migrates all vector data from ChromaDB to Qdrant with validation.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    chromadb = None

from kloros_memory.vector_store_qdrant import QdrantVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class ChromaToQdrantMigrator:
    """Migrates ChromaDB collections to Qdrant."""

    def __init__(
        self,
        chroma_dir: Path = None,
        qdrant_dir: Path = None,
        backup_dir: Path = None
    ):
        self.chroma_dir = chroma_dir or Path.home() / ".kloros" / "vectordb"
        self.qdrant_dir = qdrant_dir or Path.home() / ".kloros" / "vectordb_qdrant"
        self.backup_dir = backup_dir or Path.home() / ".kloros" / "chromadb_backup"

        self.chroma_client = None
        self.qdrant_stores: Dict[str, QdrantVectorStore] = {}

    def check_chromadb_exists(self) -> bool:
        """Check if ChromaDB data exists."""
        if not HAS_CHROMADB:
            logger.warning("ChromaDB not installed, nothing to migrate")
            return False

        if not self.chroma_dir.exists():
            logger.warning(f"ChromaDB directory not found: {self.chroma_dir}")
            return False

        return True

    def initialize_chromadb(self) -> bool:
        """Initialize ChromaDB client."""
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=False
                )
            )
            logger.info(f"Connected to ChromaDB at {self.chroma_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            return False

    def export_chromadb_collection(self, collection_name: str) -> Optional[Dict]:
        """Export a ChromaDB collection to dict format."""
        try:
            collection = self.chroma_client.get_collection(collection_name)
            count = collection.count()

            if count == 0:
                logger.info(f"Collection '{collection_name}' is empty, skipping")
                return None

            logger.info(f"Exporting {count} documents from '{collection_name}'...")

            results = collection.get(
                include=["embeddings", "documents", "metadatas"]
            )

            export_data = {
                "collection_name": collection_name,
                "count": count,
                "ids": results["ids"],
                "embeddings": results["embeddings"],
                "documents": results["documents"],
                "metadatas": results["metadatas"],
                "exported_at": datetime.now().isoformat()
            }

            logger.info(f"✓ Exported {count} documents from '{collection_name}'")
            return export_data

        except Exception as e:
            logger.error(f"Failed to export collection '{collection_name}': {e}")
            return None

    def save_backup(self, collection_data: Dict) -> Path:
        """Save collection backup to disk."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        collection_name = collection_data["collection_name"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"{collection_name}_{timestamp}.json"

        # Convert numpy arrays to lists for JSON serialization
        serializable_data = collection_data.copy()
        embeddings = serializable_data.get("embeddings")
        if embeddings is not None and len(embeddings) > 0:
            serializable_data["embeddings"] = [
                emb.tolist() if hasattr(emb, 'tolist') else emb
                for emb in embeddings
            ]

        backup_file.write_text(json.dumps(serializable_data, indent=2))
        logger.info(f"✓ Saved backup to {backup_file}")

        return backup_file

    def import_to_qdrant(self, collection_data: Dict) -> bool:
        """Import collection data into Qdrant."""
        collection_name = collection_data["collection_name"]

        try:
            if collection_name not in self.qdrant_stores:
                self.qdrant_stores[collection_name] = QdrantVectorStore(
                    persist_directory=self.qdrant_dir,
                    collection_name=collection_name
                )

            qdrant_store = self.qdrant_stores[collection_name]

            ids = collection_data["ids"]
            embeddings = collection_data["embeddings"]
            documents = collection_data["documents"]
            metadatas = collection_data["metadatas"]

            logger.info(f"Importing {len(ids)} documents to Qdrant collection '{collection_name}'...")

            batch_size = 100
            imported = 0

            for i in range(0, len(ids), batch_size):
                batch_end = min(i + batch_size, len(ids))

                batch_ids = ids[i:batch_end]
                batch_embeddings = embeddings[i:batch_end]
                batch_documents = documents[i:batch_end]
                batch_metadatas = metadatas[i:batch_end]

                qdrant_store.add_batch(
                    texts=batch_documents,
                    doc_ids=batch_ids,
                    metadatas=batch_metadatas,
                    embeddings=batch_embeddings
                )

                imported += len(batch_ids)
                logger.info(f"  Imported {imported}/{len(ids)} documents...")

            logger.info(f"✓ Imported {imported} documents to Qdrant collection '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to import to Qdrant: {e}", exc_info=True)
            return False

    def validate_migration(self, collection_data: Dict) -> bool:
        """Validate that Qdrant has all the data."""
        collection_name = collection_data["collection_name"]
        expected_count = collection_data["count"]

        qdrant_store = self.qdrant_stores.get(collection_name)
        if not qdrant_store:
            logger.error(f"Qdrant store for '{collection_name}' not found")
            return False

        actual_count = qdrant_store.count()

        if actual_count != expected_count:
            logger.error(
                f"❌ Validation failed: Expected {expected_count} documents, "
                f"got {actual_count} in Qdrant"
            )
            return False

        sample_id = collection_data["ids"][0]
        doc = qdrant_store.get(sample_id)
        if not doc:
            logger.error(f"❌ Validation failed: Sample document {sample_id} not found")
            return False

        logger.info(f"✓ Validation passed: {actual_count} documents in Qdrant")
        return True

    def migrate(self, dry_run: bool = False) -> bool:
        """Run full migration."""
        logger.info("=" * 60)
        logger.info("ChromaDB → Qdrant Migration")
        logger.info("=" * 60)

        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

        if not self.check_chromadb_exists():
            logger.info("No ChromaDB data found, creating fresh Qdrant store")
            qdrant_store = QdrantVectorStore(
                persist_directory=self.qdrant_dir,
                collection_name="kloros_memory"
            )
            logger.info(f"✓ Initialized empty Qdrant store at {self.qdrant_dir}")
            return True

        if not self.initialize_chromadb():
            return False

        try:
            collections = self.chroma_client.list_collections()
            logger.info(f"Found {len(collections)} ChromaDB collections")

            if len(collections) == 0:
                logger.info("No collections to migrate, creating fresh Qdrant store")
                qdrant_store = QdrantVectorStore(
                    persist_directory=self.qdrant_dir,
                    collection_name="kloros_memory"
                )
                logger.info(f"✓ Initialized empty Qdrant store at {self.qdrant_dir}")
                return True

            migrated_collections = []

            for collection in collections:
                logger.info(f"\n--- Migrating collection: {collection.name} ---")

                export_data = self.export_chromadb_collection(collection.name)
                if not export_data:
                    continue

                backup_file = self.save_backup(export_data)

                if dry_run:
                    logger.info(f"[DRY RUN] Would import to Qdrant collection '{collection.name}'")
                    migrated_collections.append(collection.name)
                    continue

                if not self.import_to_qdrant(export_data):
                    logger.error(f"Failed to migrate collection '{collection.name}'")
                    continue

                if not self.validate_migration(export_data):
                    logger.error(f"Validation failed for collection '{collection.name}'")
                    continue

                migrated_collections.append(collection.name)
                logger.info(f"✓ Successfully migrated '{collection.name}'")

            logger.info("\n" + "=" * 60)
            logger.info("Migration Summary")
            logger.info("=" * 60)
            logger.info(f"Total collections: {len(collections)}")
            logger.info(f"Successfully migrated: {len(migrated_collections)}")
            logger.info(f"Backup location: {self.backup_dir}")
            logger.info(f"Qdrant location: {self.qdrant_dir}")

            if len(migrated_collections) == len(collections):
                logger.info("\n✅ All collections migrated successfully!")
                return True
            else:
                logger.warning("\n⚠️  Some collections failed to migrate")
                return False

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate ChromaDB to Qdrant")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes"
    )
    parser.add_argument(
        "--chroma-dir",
        type=Path,
        help="ChromaDB directory (default: ~/.kloros/vectordb)"
    )
    parser.add_argument(
        "--qdrant-dir",
        type=Path,
        help="Qdrant directory (default: ~/.kloros/vectordb_qdrant)"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Backup directory (default: ~/.kloros/chromadb_backup)"
    )

    args = parser.parse_args()

    migrator = ChromaToQdrantMigrator(
        chroma_dir=args.chroma_dir,
        qdrant_dir=args.qdrant_dir,
        backup_dir=args.backup_dir
    )

    success = migrator.migrate(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
