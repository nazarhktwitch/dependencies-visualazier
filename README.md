# **Dependencies Visualizer**  

**A simple but powerful tool to visualize dependencies in your codebase.**  

This tool scans your project and generates an interactive graph showing how files depend on each other across multiple programming languages.  

⚠ **Note:** This is a **beta** version! It might:  

- Miss some dependencies in complex projects  
- Be slow on very large codebases  
- Have occasional bugs  

---

## **📦 Supported Languages**  

| Language     | File Extensions        |  
|--------------|------------------------|  
| Go (Golang)  | `.go`, `_test.go`      |  
| Java         | `.java`                |  
| Python       | `.py`                  |  
| JavaScript   | `.js`, `.jsx`, `.mjs`  |  
| TypeScript   | `.ts`, `.tsx`          |  
| C            | `.c`, `.h`             |  
| C++          | `.cpp`, `.hpp`, etc.   |  
| Rust         | `.rs`                  |  
| Ruby         | `.rb`                  |  
| PHP          | `.php`                 |  
| C#           | `.cs`                  |  
| Kotlin       | `.kt`                  |  
| Swift        | `.swift`               |  

---

## **⚙ Installation**  

1. **Install Python 3.7+** (if not already installed)  
2. **Install dependencies:**  
   ```bash
   pip install pyvis tqdm
   ```
   **Or using requirements.txt (First complete step 3):**
   ```bash
   pip install -r requirements.txt
   ```
4. **Download the script (Or .zip):**  
   ```bash
   curl -O https://raw.githubusercontent.com/nazarhktwitch/dependencies-visualizer/main/main.py
   ```

   **Or with Git (You must have Git installed in your system):**
   ```bash
   git clone https://github.com/nazarhktwitch/dependencies-visualizer/
   ```

   **(For Git method (Windows):**
   ```bash
   cd dependencies-visualizer
   ```

---

## **🚀 Usage**  

### **Basic Command**
```bash
python visualizer.py /path/to/your/project
```

### **Options**
 
| Flag                  | Description                          |  
|-----------------------|--------------------------------------|  
| `-o output.html`      | Custom output filename               |  
| `--exclude dir1 dir2` | Skip specific directories            |  

**Example:**

```bash
python main.py ~/my_project -o deps.html --exclude node_modules build
```

---

## **🔍 How It Works**  

1. **Scans** your project for imports/includes in supported languages.  
2. **Builds a graph** showing file relationships.  
3. **Generates an interactive HTML visualization** (open in browser).  

---

## **⚠ Known Limitations**  

- **Large projects** (>10k files) may take time to process.  
- **External dependencies** (like npm packages) are shown as-is.  
- **Some edge cases** might be missed (dynamic imports, macros, etc.).  

---

## **💡 Tips for Better Results**  

✅ **Exclude build folders** (`--exclude node_modules build`)  
✅ **Run in a smaller subdirectory first** for testing  
✅ **Check the console output** for warnings  

---

## **📄 License**

MIT License - Free to use and modify.
