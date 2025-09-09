#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

try:
    import requests
    import json
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages using: pip install -r requirements.txt")
    sys.exit(1)


class ModernMarkdownToPDFConverter:
    def __init__(self, input_file: str, output_file: str = None):
        self.input_file = input_file
        self.output_file = output_file or self._generate_output_filename()
        self.temp_dir = tempfile.mkdtemp()
        self.template_file = Path(__file__).parent / 'template.html'
        
    def _generate_output_filename(self) -> str:
        """Generate output PDF filename based on input file"""
        input_path = Path(self.input_file)
        return str(input_path.with_suffix('.pdf'))
    
    def _generate_html_filename(self) -> str:
        """Generate HTML filename based on input file"""
        input_path = Path(self.input_file)
        return str(input_path.with_suffix('.html'))
    
    def _prepare_working_directory(self) -> str:
        """Prepare working directory with template and markdown file"""
        # Copy template to working directory
        template_dest = os.path.join(self.temp_dir, 'template.html')
        shutil.copy2(self.template_file, template_dest)
        
        # Copy markdown file to working directory
        markdown_dest = os.path.join(self.temp_dir, os.path.basename(self.input_file))
        shutil.copy2(self.input_file, markdown_dest)
        
        # Copy any image files referenced in the markdown
        self._copy_referenced_files()
        
        return template_dest
    
    def _copy_referenced_files(self):
        """Copy image files and other assets referenced in the markdown"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find image references
            image_pattern = r'!\[.*?\]\(([^)]+)\)'
            for match in re.finditer(image_pattern, content):
                image_path = match.group(1)
                if os.path.exists(image_path):
                    dest_path = os.path.join(self.temp_dir, os.path.basename(image_path))
                    shutil.copy2(image_path, dest_path)
                    print(f"Copied image: {image_path} -> {dest_path}")
        except Exception as e:
            print(f"Warning: Could not copy referenced files: {e}")
    
    def _escape_for_javascript(self, text: str) -> str:
        """
        Escape text for safe embedding in JavaScript template literals.
        This function handles all special characters that could break JavaScript.
        """
        if not text:
            return ""
        
        # Convert to string if not already
        text = str(text)
        
        # Escape characters that are problematic in JavaScript template literals
        # Order matters - escape backslashes first
        escaped = text.replace('\\', '\\\\')  # Escape backslashes
        escaped = escaped.replace('`', '\\`')  # Escape backticks
        escaped = escaped.replace('${', '\\${')  # Escape template literal expressions
        escaped = escaped.replace('\r\n', '\\n')  # Windows line endings
        escaped = escaped.replace('\r', '\\n')    # Mac line endings
        escaped = escaped.replace('\n', '\\n')    # Unix line endings
        
        # Escape other potentially problematic characters
        escaped = escaped.replace('\t', '\\t')    # Tabs
        escaped = escaped.replace('\b', '\\b')    # Backspace
        escaped = escaped.replace('\f', '\\f')    # Form feed
        escaped = escaped.replace('\v', '\\v')    # Vertical tab
        
        # Escape quotes that could break the string
        escaped = escaped.replace('"', '\\"')     # Double quotes
        escaped = escaped.replace("'", "\\'")     # Single quotes
        
        return escaped
    
    def _create_html_document(self) -> str:
        """Create HTML document using the template approach with embedded markdown"""
        template_path = self._prepare_working_directory()

        # Read the template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Read the markdown content
        with open(self.input_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()


        # Use robust JavaScript string escaping that preserves Unicode
        escaped_markdown = self._escape_for_javascript(markdown_content)

        # Replace the fetch approach with embedded content
        template_content = template_content.replace(
            "const CONFIG = {\n            markdownFile: 'synth.md',\n            mermaidTheme: 'default',\n            mermaidWaitTime: 3000\n        };",
            f"const CONFIG = {{\n            markdownContent: `{escaped_markdown}`,\n            mermaidTheme: 'default',\n            mermaidWaitTime: 3000\n        }};"
        )

        # Update the loadMarkdownFile function to use embedded content
        template_content = template_content.replace(
            "async function loadMarkdownFile() {\n            try {\n                const response = await fetch(CONFIG.markdownFile);\n                if (!response.ok) {\n                    throw new Error(`HTTP error! status: ${response.status}`);\n                }\n                const markdownText = await response.text();\n                return markdownText;\n            } catch (error) {\n                console.error('Error loading markdown file:', error);\n                throw error;\n            }\n        }",
            "async function loadMarkdownFile() {\n            try {\n                return CONFIG.markdownContent;\n            } catch (error) {\n                console.error('Error loading markdown content:', error);\n                throw error;\n            }\n        }"
        )


        # Add immediate execution script to ensure content is rendered
        immediate_script = """
        <script>
        // Wait for all libraries to load before processing
        window.addEventListener('load', function() {
            console.log('All libraries loaded, starting content processing...');
            
            // Wait a bit more to ensure everything is ready
            setTimeout(function() {
                const markdownContent = CONFIG.markdownContent;
                const contentDiv = document.getElementById('content');
                const loadingDiv = document.getElementById('loading');
                
                if (contentDiv && markdownContent && typeof marked !== 'undefined') {
                    try {
                        console.log('Processing markdown content...');
                        
                        // Configure Marked.js with custom renderer
                        const renderer = new marked.Renderer();
                        
                        renderer.image = function(href, title, text) {
                            console.log('Rendering image:', {href, title, text});
                            const titleAttr = title ? ` title="${title}"` : '';
                            return `<img src="${href}" alt="${text}"${titleAttr} style="display: inline-block; margin: 2px; border: none; max-height: 20px;">`;
                        };
                        
                        renderer.link = function(href, title, text) {
                            console.log('Rendering link:', {href, title, text});
                            const titleAttr = title ? ` title="${title}"` : '';
                            return `<a href="${href}"${titleAttr}>${text}</a>`;
                        };
                        
                        marked.setOptions({ 
                            renderer: renderer,
                            breaks: true,
                            gfm: true,
                            pedantic: false,
                            sanitize: false,
                            smartLists: true,
                            smartypants: false
                        });
                        
                        // Parse markdown
                        console.log('Markdown content length:', markdownContent.length);
                        console.log('Markdown content preview:', markdownContent.substring(0, 500));
                        const htmlContent = marked.parse(markdownContent);
                        console.log('Parsed HTML length:', htmlContent.length);
                        contentDiv.innerHTML = htmlContent;
                        
                        // Hide loading, show content
                        loadingDiv.style.display = 'none';
                        contentDiv.style.display = 'block';
                        
                        // Highlight code blocks
                        if (typeof Prism !== 'undefined') {
                            Prism.highlightAll();
                        }
                        
                        console.log('Content processed successfully');
                    } catch (error) {
                        console.error('Error in content processing:', error);
                        loadingDiv.innerHTML = `<div class="error">Error processing content: ${error.message}</div>`;
                    }
                } else {
                    console.error('Missing dependencies:', {
                        contentDiv: !!contentDiv,
                        markdownContent: !!markdownContent,
                        marked: typeof marked
                    });
                }
            }, 1000);
        });
        </script>
        """
        
        # Add CSS for proper badge rendering and image sizing
        badge_css = """
        <style>
        /* Ensure badges render as images, not text */
        img[src*="img.shields.io"] {
            display: inline-block !important;
            margin: 2px 4px !important;
            border: none !important;
            max-height: 20px !important;
            vertical-align: middle !important;
        }
        
        /* Make document images larger and more readable */
        .markdown-body img:not([src*="img.shields.io"]) {
            max-width: 100% !important;
            height: auto !important;
            display: block !important;
            margin: 20px auto !important;
            border: 1px solid #ddd !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
            min-height: 200px !important;
        }
        
        /* Specific styling for screenshots */
        img[src*="xml-1.png"], img[src*="xml2.png"], img[src*="discount_breakdown.jpeg"] {
            width: 90% !important;
            height: auto !important;
            max-width: none !important;
            min-height: auto !important;
            object-fit: contain !important;
        }
        
        /* Fix emoji rendering */
        .markdown-body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif !important;
        }
        </style>
        """
        
        # Insert CSS before closing head tag and script before closing body tag
        template_content = template_content.replace('</head>', badge_css + '</head>')
        template_content = template_content.replace('</body>', immediate_script + '</body>')

        return template_content
    
    def _convert_html_to_pdf_with_chrome(self, html_file: str) -> None:
        """Convert HTML to PDF using Chrome headless with enhanced waiting for JavaScript"""
        
        # Try different Chrome paths
        chrome_paths = [
            'google-chrome',
            'chromium',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser'
        ]
        
        chrome_cmd_base = [
            '--headless',
            '--disable-gpu',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-extensions',
            '--disable-plugins',
            '--print-to-pdf=' + self.output_file,
            '--print-to-pdf-no-header',
            '--print-to-pdf-no-footer',
            '--disable-print-preview',
            '--run-all-compositor-stages-before-draw',
            '--virtual-time-budget=20000',  # Wait 20 seconds for JavaScript to complete
            '--margin-top=1cm',
            '--margin-bottom=1cm',
            '--margin-left=1cm',
            '--margin-right=1cm',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--allow-file-access-from-files',  # Allow local file access
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            html_file
        ]
        
        success = False
        last_error = None
        
        for chrome_path in chrome_paths:
            try:
                chrome_cmd = [chrome_path] + chrome_cmd_base
                print(f"Trying Chrome path: {chrome_path}")
                print(f"Converting HTML to PDF with enhanced JavaScript support...")
                # Add a delay to ensure JavaScript execution
                import time

                result = subprocess.run(chrome_cmd, capture_output=True, text=True, timeout=90)
                if result.returncode == 0:
                    success = True
                    break
                else:
                    last_error = result.stderr
                    print(f"Chrome error with {chrome_path}: {result.stderr}")
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                print(f"Chrome timeout with {chrome_path}")
                continue
        
        if not success:
            print("Error: Chrome/Chromium not found. Please install Chrome or Chromium.")
            print("On macOS: brew install --cask google-chrome")
            print("On Ubuntu: sudo apt-get install google-chrome-stable")
            print("On macOS: brew install chromium")
            print("On Ubuntu: sudo apt-get install chromium-browser")
            if last_error:
                print(f"Last error: {last_error}")
            raise Exception("No working Chrome/Chromium installation found")
    
    def convert(self):
        """Main conversion method using JavaScript-based approach"""
        try:
            print(f"Processing {self.input_file}...")
            print("Using JavaScript-based markdown conversion with Mermaid support...")
            
            # Check if template exists
            if not self.template_file.exists():
                raise FileNotFoundError(f"Template file not found: {self.template_file}")
            
            # Create HTML document using template approach
            full_html = self._create_html_document()
            
            # Generate HTML file name
            html_file = self._generate_html_filename()
            
            # Save HTML file
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(full_html)
            print(f"HTML file created: {html_file}")
            
            # Convert HTML to PDF using Chrome with enhanced JavaScript support
            print("Converting to PDF using Chrome with JavaScript rendering...")
            self._convert_html_to_pdf_with_chrome(html_file)
            
            print(f"PDF created successfully: {self.output_file}")
            
            # Cleanup temporary directory
            try:
                if os.path.exists(self.temp_dir):
                    shutil.rmtree(self.temp_dir)
            except OSError:
                # Directory not empty, ignore
                pass
                
        except Exception as e:
            print(f"Error converting file: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="JavaScript-based Markdown to PDF converter with Mermaid support using Chrome"
    )
    parser.add_argument(
        'file',
        nargs='?',
        default='README.md',
        help='Input markdown file (default: README.md)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output PDF file path'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.file):
        print(f"Error: Input file '{args.file}' not found")
        sys.exit(1)
    
    # Create converter and convert
    converter = ModernMarkdownToPDFConverter(args.file, args.output)
    converter.convert()


if __name__ == "__main__":
    main()
