import os
import re
import argparse
import json
import sys
from typing import Dict, Set, List, Optional, Tuple
from pyvis.network import Network
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from tqdm import tqdm

# ====================== CONFIGURATION ======================
USE_PARALLEL_PROCESSING = True  # Enable/disable parallel processing
MAX_WORKERS = multiprocessing.cpu_count() * 2  # Optimal number of workers
CHUNK_SIZE = 100  # Number of files to process in each batch
SHOW_PROGRESS = True  # Show progress bar during processing
# ===========================================================

class DependencyVisualizer:
    def __init__(self):
        self.dependencies: Dict[str, Set[str]] = {}
        self.aliases: Dict[str, str] = {}
        self.exclude_dirs = {
            'bin', 'obj', 'node_modules', 'venv', '.git', '__pycache__',
            'packages', '.vs', 'build', 'dist', 'Debug', 'Release',
            'lib', 'cmake-build-debug', 'cmake-build-release', 'target'
        }
        self.file_extensions = {
            'c': ['.c', '.h'],
            'cpp': ['.cpp', '.hpp', '.cc', '.hh', '.cxx', '.hxx'],
            'csharp': ['.cs'],
            'python': ['.py'],
            'javascript': ['.js', '.jsx', '.mjs', '.cjs'],
            'typescript': ['.ts', '.tsx'],
            'rust': ['.rs'],
            'go': ['.go'],
            'java': ['.java'],
            'kotlin': ['.kt']
        }
        
        self.import_patterns = {}
        self._init_patterns()
        self.stats = {
            'files_processed': 0,
            'dependencies_found': 0,
            'errors': 0,
            'warnings': 0,
            'skipped': 0
        }
        self._lock = multiprocessing.Lock() if USE_PARALLEL_PROCESSING else None

    def _init_patterns(self):
        """Initialize regex patterns for different languages"""
        self.import_patterns = {
            'c': [
                (re.compile(r'^\s*#include\s+"([^"]+)"'), 'local'),
                (re.compile(r'^\s*#include\s+<([^>]+)>'), 'system')
            ],
            'cpp': [
                (re.compile(r'^\s*#include\s+"([^"]+)"'), 'local'),
                (re.compile(r'^\s*#include\s+<([^>]+)>'), 'system'),
                (re.compile(r'^\s*import\s+([^;]+);'), 'module'),
                (re.compile(r'^\s*module\s+([^;]+);'), 'module')
            ],
            'csharp': [
                (re.compile(r'^\s*using\s+([\w.]+)\s*;'), 'namespace'),
                (re.compile(r'^\s*using\s+static\s+([\w.]+)\s*;'), 'static'),
                (re.compile(r'^\s*namespace\s+([\w.]+)'), 'declaration')
            ],
            'python': [
                (re.compile(r'^\s*(?:from\s+([\w.]+)\s+)?import\s+([\w.]+)'), 'import'),
                (re.compile(r'^\s*import\s+([\w., ]+)'), 'multi_import')
            ],
            'javascript': [
                (re.compile(r'require\([\'"]([^"\']+)[\'"]\)'), 'require'),
                (re.compile(r'from\s+[\'"]([^"\']+)[\'"]'), 'from'),
                (re.compile(r'import\s+[\'"]([^"\']+)[\'"]'), 'import'),
                (re.compile(r'import\([\'"]([^"\']+)[\'"]\)'), 'dynamic_import')
            ],
            'typescript': [
                (re.compile(r'import\s+[\'"]([^"\']+)[\'"]'), 'import'),
                (re.compile(r'type\s+\w+\s*=\s*import\([\'"]([^"\']+)[\'"]\)'), 'type_import')
            ],
            'rust': [
                (re.compile(r'^\s*use\s+([\w:{}, ]+)'), 'use'),
                (re.compile(r'^\s*mod\s+([\w]+)'), 'mod')
            ],
            'go': [
                (re.compile(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"'), 'import')
            ]
        }

    def _log_error(self, message: str, file: str = None, exception: Exception = None):
        """Log an error with detailed context"""
        self.stats['errors'] += 1
        error_msg = f"ERROR: {message}"
        if file:
            error_msg += f" | File: {file}"
        if exception:
            error_msg += f" | Exception: {str(exception)}"
        print(error_msg, file=sys.stderr)

    def _log_warning(self, message: str, file: str = None):
        """Log a warning with context"""
        self.stats['warnings'] += 1
        warning_msg = f"WARNING: {message}"
        if file:
            warning_msg += f" | File: {file}"
        print(warning_msg, file=sys.stderr)

    def _log_info(self, message: str):
        """Log informational message"""
        print(f"INFO: {message}")

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        for lang, exts in self.file_extensions.items():
            if ext in exts:
                return lang
        return None

    def _clean_json_content(self, content: str) -> str:
        """Clean JSON content by removing comments and trailing commas"""
        # Remove single-line comments
        content = re.sub(r'//.*?\n', '\n', content)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove trailing commas
        content = re.sub(r',\s*([}\]])', r'\1', content)
        return content

    def _parse_config_file(self, config_path: str) -> Optional[dict]:
        """Parse configuration file with error handling"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                cleaned_content = self._clean_json_content(content)
                return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            self._log_error(f"Invalid JSON in {config_path}", exception=e)
        except Exception as e:
            self._log_error(f"Failed to read {config_path}", exception=e)
        return None

    def load_config(self, project_root: str):
        """Load project configuration files"""
        # Load C/C++ configuration from CMake
        cmake_path = os.path.join(project_root, 'CMakeLists.txt')
        if os.path.exists(cmake_path):
            try:
                with open(cmake_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    include_dirs = re.findall(r'include_directories\((.*?)\)', content, re.DOTALL)
                    for dirs in include_dirs:
                        for d in re.split(r'\s+', dirs.strip()):
                            if d and os.path.exists(os.path.join(project_root, d)):
                                self.aliases[d] = os.path.normpath(os.path.join(project_root, d))
                                self._log_info(f"Added include directory: {d}")
            except Exception as e:
                self._log_error(f"Failed to parse CMakeLists.txt", exception=e)

        # Load C# project references
        for csproj_file in self._find_files(project_root, '*.csproj'):
            try:
                with open(csproj_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    project_refs = re.findall(r'<ProjectReference\s+Include="([^"]+)"', content)
                    for ref in project_refs:
                        ref_path = os.path.normpath(os.path.join(os.path.dirname(csproj_file), ref))
                        project_name = os.path.splitext(os.path.basename(ref_path))[0]
                        self.aliases[project_name] = ref_path
                        self._log_info(f"Added C# project reference: {project_name} -> {ref_path}")
            except Exception as e:
                self._log_error(f"Failed to parse {csproj_file}", exception=e)

        # Load TypeScript/JavaScript configuration
        for config_name in ['tsconfig.json', 'jsconfig.json']:
            config_path = os.path.join(project_root, config_name)
            if os.path.exists(config_path):
                config = self._parse_config_file(config_path)
                if config and 'compilerOptions' in config and 'paths' in config['compilerOptions']:
                    for alias, paths in config['compilerOptions']['paths'].items():
                        if paths and isinstance(paths, list):
                            clean_alias = alias.replace('/*', '')
                            clean_path = paths[0].replace('/*', '')
                            self.aliases[clean_alias] = clean_path
                            self._log_info(f"Added path alias: {clean_alias} -> {clean_path}")

    def _find_files(self, root: str, pattern: str) -> List[str]:
        """Find files matching pattern in directory tree"""
        matches = []
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower().endswith(pattern.lower().replace('*', '')):
                    matches.append(os.path.join(dirpath, filename))
        return matches

    def resolve_alias(self, dep: str, current_file_dir: str, language: str) -> str:
        """Resolve import path using aliases and language-specific rules"""
        try:
            # C/C++: Handle local includes
            if language in ['c', 'cpp'] and dep.startswith('"'):
                dep = dep.strip('"')
                abs_path = os.path.normpath(os.path.join(current_file_dir, dep))
                if os.path.exists(abs_path):
                    return abs_path
            
            # C#: Convert namespace to path
            if language == 'csharp' and '.' in dep and not dep.endswith('.cs'):
                return dep.replace('.', '/') + '.cs'
            
            # Check aliases
            for alias, path in self.aliases.items():
                if dep.startswith(alias):
                    return dep.replace(alias, path)
            
            # Handle relative paths
            if dep.startswith(('.', '/')):
                abs_path = os.path.normpath(os.path.join(current_file_dir, dep))
                return abs_path
            
            return dep
        except Exception as e:
            self._log_error(f"Failed to resolve alias for '{dep}'", exception=e)
            return dep

    def extract_dependencies(self, file_path: str, content: str) -> Set[str]:
        """Extract dependencies from file content"""
        language = self.detect_language(file_path)
        if not language or language not in self.import_patterns:
            return set()

        dependencies = set()
        current_dir = os.path.dirname(file_path)

        for pattern, pattern_type in self.import_patterns[language]:
            try:
                for line in content.split('\n'):
                    matches = pattern.finditer(line)
                    for match in matches:
                        for group in match.groups():
                            if group:
                                # Skip system headers in C/C++
                                if language in ['c', 'cpp'] and pattern_type == 'system':
                                    continue
                                    
                                # Handle multiple imports in one line
                                for dep in re.split(r'\s*,\s*', group.strip()):
                                    if dep:
                                        # Clean up dependency string
                                        dep = re.sub(r'[\{\}\*\s;]', '', dep.split('//')[0].split('/*')[0].strip())
                                        if dep:
                                            resolved = self.resolve_alias(dep, current_dir, language)
                                            if resolved:
                                                dependencies.add(resolved)
            except Exception as e:
                self._log_error(f"Failed to extract dependencies from {file_path}", exception=e)

        return dependencies

    def should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from analysis"""
        path_parts = path.split(os.sep)
        return any(exclude_dir in path_parts for exclude_dir in self.exclude_dirs)

    def scan_project(self, project_root: str):
        """Scan the entire project directory"""
        self._log_info(f"Starting scan of project at {project_root}")
        self.load_config(project_root)

        # Collect all files to process
        files_to_process = []
        for root, dirs, files in os.walk(project_root):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if not self.should_exclude(os.path.join(root, d))]
            
            for file in files:
                file_path = os.path.join(root, file)
                if any(file_path.endswith(ext) for exts in self.file_extensions.values() for ext in exts):
                    files_to_process.append(file_path)

        if USE_PARALLEL_PROCESSING:
            self._log_info(f"Using parallel processing with {MAX_WORKERS} workers")
            self._parallel_process_files(files_to_process, project_root)
        else:
            self._log_info("Using sequential processing")
            if SHOW_PROGRESS:
                for file_path in tqdm(files_to_process, desc="Processing files"):
                    self._process_file_single(file_path, project_root)
            else:
                for file_path in files_to_process:
                    self._process_file_single(file_path, project_root)

        self._log_info(f"Scan completed. Processed {self.stats['files_processed']} files, "
                      f"found {self.stats['dependencies_found']} dependencies")
        self._log_info(f"Encountered {self.stats['errors']} errors and {self.stats['warnings']} warnings")
        self._log_info(f"Skipped {self.stats['skipped']} files")

    def _parallel_process_files(self, file_paths: List[str], project_root: str):
        """Process files in parallel batches"""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Process files in chunks to balance memory usage
            if SHOW_PROGRESS:
                pbar = tqdm(total=len(file_paths), desc="Processing files")
            
            for i in range(0, len(file_paths), CHUNK_SIZE):
                chunk = file_paths[i:i + CHUNK_SIZE]
                futures = {
                    executor.submit(self._process_file_wrapper, fp, project_root): fp
                    for fp in chunk
                }
                
                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        result = future.result()
                        if result:
                            rel_path, deps = result
                            with self._lock:
                                self.dependencies[rel_path] = deps
                                self.stats['files_processed'] += 1
                                self.stats['dependencies_found'] += len(deps)
                        else:
                            with self._lock:
                                self.stats['skipped'] += 1
                    except Exception as e:
                        with self._lock:
                            self.stats['errors'] += 1
                        self._log_error(f"Failed to process {file_path}", exception=e)
                    
                    if SHOW_PROGRESS:
                        pbar.update(1)
            
            if SHOW_PROGRESS:
                pbar.close()

    def _process_file_single(self, file_path: str, project_root: str):
        """Process a single file in sequential mode"""
        if self.should_exclude(file_path):
            self.stats['skipped'] += 1
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                self.stats['errors'] += 1
                self._log_error(f"Failed to read file {file_path}", exception=e)
                return
        except Exception as e:
            self.stats['errors'] += 1
            self._log_error(f"Error opening file {file_path}", exception=e)
            return

        rel_path = os.path.relpath(file_path, project_root)
        dependencies = self.extract_dependencies(file_path, content)

        # Normalize paths
        normalized_deps = set()
        for dep in dependencies:
            try:
                if dep.startswith(('.', '/')):
                    abs_dep = os.path.normpath(os.path.join(os.path.dirname(file_path), dep))
                    if os.path.exists(abs_dep):
                        if os.path.isdir(abs_dep):
                            # Look for index files in directories
                            lang = self.detect_language(file_path)
                            if lang:
                                for ext in self.file_extensions[lang]:
                                    index_file = os.path.join(abs_dep, f'index{ext}')
                                    if os.path.exists(index_file):
                                        abs_dep = index_file
                                        break
                        if os.path.exists(abs_dep):
                            dep = os.path.relpath(abs_dep, project_root)

                if not any(exclude_dir in dep for exclude_dir in self.exclude_dirs):
                    normalized_deps.add(dep)
            except Exception as e:
                self.stats['errors'] += 1
                self._log_error(f"Failed to normalize path {dep}", exception=e)

        if normalized_deps:
            self.dependencies[rel_path] = normalized_deps
            self.stats['dependencies_found'] += len(normalized_deps)
        self.stats['files_processed'] += 1

    def _process_file_wrapper(self, file_path: str, project_root: str) -> Optional[Tuple[str, Set[str]]]:
        """Wrapper for parallel file processing"""
        if self.should_exclude(file_path):
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                self._log_error(f"Failed to read file {file_path}", exception=e)
                return None
        except Exception as e:
            self._log_error(f"Error opening file {file_path}", exception=e)
            return None

        rel_path = os.path.relpath(file_path, project_root)
        dependencies = self.extract_dependencies(file_path, content)

        # Normalize paths
        normalized_deps = set()
        for dep in dependencies:
            try:
                if dep.startswith(('.', '/')):
                    abs_dep = os.path.normpath(os.path.join(os.path.dirname(file_path), dep))
                    if os.path.exists(abs_dep):
                        if os.path.isdir(abs_dep):
                            # Look for index files in directories
                            lang = self.detect_language(file_path)
                            if lang:
                                for ext in self.file_extensions[lang]:
                                    index_file = os.path.join(abs_dep, f'index{ext}')
                                    if os.path.exists(index_file):
                                        abs_dep = index_file
                                        break
                        if os.path.exists(abs_dep):
                            dep = os.path.relpath(abs_dep, project_root)

                if not any(exclude_dir in dep for exclude_dir in self.exclude_dirs):
                    normalized_deps.add(dep)
            except Exception as e:
                self._log_error(f"Failed to normalize path {dep}", exception=e)

        return (rel_path, normalized_deps) if normalized_deps else None

    def generate_graph(self, output_file: str = 'dependencies.html'):
        """Generate interactive dependency graph"""
        if not self.dependencies:
            self._log_error("No dependencies found to visualize")
            return

        self._log_info("Generating dependency graph...")
        
        try:
            net = Network(
                height='900px',
                width='100%',
                directed=True,
                notebook=False,
                cdn_resources='in_line',
                bgcolor='#222222',
                font_color='white'
            )
            
            # Add nodes
            all_nodes = set(self.dependencies.keys())
            for deps in self.dependencies.values():
                all_nodes.update(deps)
            
            # Color coding by language
            lang_colors = {
                'c': '#555555',
                'cpp': '#f34b7d',
                'csharp': '#178600',
                'python': '#3572A5',
                'javascript': '#f1e05a',
                'typescript': '#3178c6',
                'rust': '#dea584',
                'go': '#00add8',
                'java': '#b07219',
                'kotlin': '#a97bff'
            }
            
            if SHOW_PROGRESS:
                all_nodes = tqdm(all_nodes, desc="Creating nodes")

            for node in all_nodes:
                lang = self.detect_language(node) if '.' in node else 'unknown'
                color = lang_colors.get(lang, '#666666')
                net.add_node(
                    node, 
                    label=node, 
                    shape='box',
                    color=color,
                    font={'size': 12},
                    title=f"Type: {lang}" if lang != 'unknown' else "Type: unknown"
                )
            
            # Add edges
            if SHOW_PROGRESS:
                items = tqdm(self.dependencies.items(), desc="Creating edges")
            else:
                items = self.dependencies.items()

            for module, deps in items:
                for dep in deps:
                    if dep in all_nodes:
                        net.add_edge(module, dep, width=0.5)
            
            # Configure physics
            net.set_options("""
            {
                "physics": {
                    "forceAtlas2Based": {
                        "gravitationalConstant": -100,
                        "centralGravity": 0.02,
                        "springLength": 150,
                        "springConstant": 0.05,
                        "damping": 0.4
                    },
                    "minVelocity": 0.75,
                    "solver": "forceAtlas2Based",
                    "stabilization": {
                        "enabled": true,
                        "iterations": 1000
                    }
                },
                "nodes": {
                    "borderWidth": 1,
                    "borderWidthSelected": 2,
                    "shadow": {
                        "enabled": true
                    }
                },
                "edges": {
                    "smooth": {
                        "type": "continuous"
                    },
                    "arrows": {
                        "to": {
                            "enabled": true,
                            "scaleFactor": 0.5
                        }
                    }
                }
            }
            """)
            
            # Save graph
            html = net.generate_html()
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            self._log_info(f"Successfully generated dependency graph: {output_file}")
            self._log_info("Open this file in your browser to view the interactive graph")
            
        except Exception as e:
            self._log_error("Failed to generate dependency graph", exception=e)
            # Try saving to desktop as fallback
            try:
                desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop', os.path.basename(output_file))
                with open(desktop_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                self._log_info(f"Saved graph to desktop instead: {desktop_path}")
            except Exception as e2:
                self._log_error("Failed to save graph to desktop", exception=e2)

def main():
    parser = argparse.ArgumentParser(
        description='Advanced Project Dependency Visualizer',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        'project_path', 
        help='Path to the project directory'
    )
    parser.add_argument(
        '-o', '--output', 
        default='dependencies.html',
        help='Output HTML file name'
    )
    parser.add_argument(
        '--exclude',
        nargs='+',
        default=[],
        help='Additional directories to exclude (comma separated)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--no-parallel',
        action='store_true',
        help='Disable parallel processing'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    args = parser.parse_args()
    
    global USE_PARALLEL_PROCESSING, SHOW_PROGRESS
    USE_PARALLEL_PROCESSING = not args.no_parallel
    SHOW_PROGRESS = not args.no_progress
    
    visualizer = DependencyVisualizer()
    if args.exclude:
        visualizer.exclude_dirs.update(set(args.exclude))
    
    try:
        visualizer.scan_project(args.project_path)
        visualizer.generate_graph(args.output)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()