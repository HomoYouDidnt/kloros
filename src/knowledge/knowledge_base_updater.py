#!/usr/bin/env python3
"""Knowledge Base Updater - Allows KLoROS to update her own documentation."""

import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

class KnowledgeBaseUpdater:
    """Manages updates to the knowledge base and RAG rebuild."""
    
    def __init__(self):
        self.kb_dir = Path('/home/kloros/knowledge_base')
        self.rebuild_script = Path('/home/kloros/scripts/build_knowledge_base_rag.py')
        self.venv_python = Path('/home/kloros/.venv/bin/python3')
        
    def update_documentation(self, category: str, filename: str, content: str, 
                            reason: str = "Documentation update") -> dict:
        """Add or update documentation in knowledge base.
        
        Args:
            category: Category subdirectory (system, tools, components, troubleshooting)
            filename: Documentation filename (without .md extension)
            content: Markdown content to write
            reason: Reason for update (logged in header)
            
        Returns:
            dict with status, path, and message
        """
        try:
            # Validate category
            valid_categories = ['system', 'tools', 'components', 'troubleshooting']
            if category not in valid_categories:
                return {
                    'status': 'error',
                    'message': f"Invalid category. Must be one of: {', '.join(valid_categories)}"
                }
            
            # Create category directory if needed
            category_dir = self.kb_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure filename has .md extension
            if not filename.endswith('.md'):
                filename = f"{filename}.md"
            
            doc_path = category_dir / filename
            
            # Add metadata header if not present
            if not content.startswith('---'):
                timestamp = datetime.now().isoformat()
                metadata_header = f"""---
updated: {timestamp}
reason: {reason}
source: KLoROS self-documentation
---

"""
                content = metadata_header + content
            
            # Write documentation
            doc_path.write_text(content, encoding='utf-8')
            
            return {
                'status': 'success',
                'path': str(doc_path),
                'message': f"Documentation written to {doc_path.relative_to(self.kb_dir)}"
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Failed to write documentation: {e}"
            }
    
    def rebuild_rag_database(self) -> dict:
        """Rebuild RAG database from current knowledge base.
        
        Returns:
            dict with status and message
        """
        try:
            if not self.rebuild_script.exists():
                return {
                    'status': 'error',
                    'message': f"Rebuild script not found: {self.rebuild_script}"
                }
            
            # Run rebuild script
            result = subprocess.run(
                [str(self.venv_python), str(self.rebuild_script)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Extract stats from output
                output_lines = result.stdout.split('\n')
                stats = {}
                for line in output_lines:
                    if 'Total chunks:' in line:
                        stats['chunks'] = line.split(':')[1].strip()
                    elif 'Bundle size:' in line:
                        stats['size'] = line.split(':')[1].strip()
                
                return {
                    'status': 'success',
                    'message': 'RAG database rebuilt successfully',
                    'stats': stats,
                    'output': result.stdout
                }
            else:
                return {
                    'status': 'error',
                    'message': f"Rebuild failed with code {result.returncode}",
                    'error': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'message': 'Rebuild timed out after 120 seconds'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Rebuild failed: {e}"
            }
    
    def document_improvement(self, improvement_type: str, title: str, 
                            description: str, solution: Optional[str] = None) -> dict:
        """Document a system improvement.
        
        Args:
            improvement_type: Type of improvement (bug_fix, feature, optimization, etc.)
            title: Brief title of improvement
            description: Detailed description
            solution: Solution implemented (if applicable)
            
        Returns:
            dict with status and path
        """
        try:
            # Create improvement document
            timestamp = datetime.now().strftime('%Y-%m-%d')
            filename = f"{improvement_type}_{title.lower().replace(' ', '_')}.md"
            
            content = f"# {title}\n\n"
            content += f"**Type**: {improvement_type}\n"
            content += f"**Date**: {timestamp}\n\n"
            content += f"## Description\n{description}\n\n"
            
            if solution:
                content += f"## Solution\n{solution}\n\n"
            
            # Write to components category
            result = self.update_documentation(
                category='components',
                filename=filename,
                content=content,
                reason=f"Documented {improvement_type}: {title}"
            )
            
            if result['status'] == 'success':
                # Automatically rebuild RAG
                rebuild_result = self.rebuild_rag_database()
                result['rag_rebuild'] = rebuild_result
            
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Failed to document improvement: {e}"
            }

# Module-level instance for easy access
_updater_instance = None

def get_updater() -> KnowledgeBaseUpdater:
    """Get singleton updater instance."""
    global _updater_instance
    if _updater_instance is None:
        _updater_instance = KnowledgeBaseUpdater()
    return _updater_instance
