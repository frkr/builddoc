#!/usr/bin/env python3

import argparse
import os
import re
import tempfile
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

try:
    import markdown
    from markdown.extensions import codehilite, fenced_code, tables, nl2br
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.utils import ImageReader
    from bs4 import BeautifulSoup
    import base64
    import io
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages using: pip install -r requirements.txt")
    sys.exit(1)


class GitHubMarkdownToPDFConverter:
    def __init__(self, input_file: str, output_file: str = None, preserve_png: bool = True):
        self.input_file = input_file
        self.output_file = output_file or self._generate_output_filename()
        self.temp_dir = tempfile.mkdtemp()
        self.mermaid_images = []
        self.preserve_png = preserve_png
        
    def _generate_output_filename(self) -> str:
        """Generate output PDF filename based on input file"""
        input_path = Path(self.input_file)
        return str(input_path.with_suffix('.pdf'))
    
    def _generate_html_filename(self) -> str:
        """Generate HTML filename based on input file"""
        input_path = Path(self.input_file)
        return str(input_path.with_suffix('.html'))
    
    def _save_html_file(self, html_content: str, html_file: str) -> None:
        """Save HTML content to file with proper styling"""
        # Create a complete HTML document with CSS styling
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fff;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 24px;
            margin-bottom: 16px;
        }}
        h1 {{
            font-size: 2em;
            border-bottom: 1px solid #eaecef;
            padding-bottom: 10px;
        }}
        h2 {{
            font-size: 1.5em;
            border-bottom: 1px solid #eaecef;
            padding-bottom: 8px;
        }}
        code {{
            background-color: #f6f8fa;
            border-radius: 3px;
            padding: 2px 4px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            font-size: 0.9em;
        }}
        pre {{
            background-color: #f6f8fa;
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            border: 1px solid #e1e4e8;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            border-radius: 0;
        }}
        blockquote {{
            border-left: 4px solid #dfe2e5;
            padding-left: 16px;
            color: #6a737d;
            margin: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}
        th, td {{
            border: 1px solid #dfe2e5;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background-color: #f6f8fa;
            font-weight: 600;
        }}
        img {{
            width: 100%;
        }}
        ul, ol {{
            padding-left: 24px;
        }}
        li {{
            margin: 4px 0;
        }}
        a {{
            color: #0366d6;
            text-decoration: none;
        }}
        a:hover {{
            color: #0366d6;
            text-decoration: underline;
        }}
        a:visited {{
            color: #0366d6;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
    
    def _extract_mermaid_diagrams(self, content: str) -> List[Tuple[str, str]]:
        """Extract Mermaid diagrams from markdown content"""
        mermaid_pattern = r'```mermaid\n(.*?)\n```'
        diagrams = []
        
        for match in re.finditer(mermaid_pattern, content, re.DOTALL):
            diagram_code = match.group(1).strip()
            diagrams.append((match.group(0), diagram_code))
            
        return diagrams
    
    def _render_mermaid_to_png(self, diagram_code: str, output_path: str) -> bool:
        """Render Mermaid diagram to PNG using mermaid-cli"""
        try:
            # Create temporary mermaid file
            mermaid_file = os.path.join(self.temp_dir, f"diagram_{len(self.mermaid_images)}.mmd")
            with open(mermaid_file, 'w') as f:
                f.write(diagram_code)
            
            # Use mermaid-cli to render to PNG with white background
            cmd = [
                'mmdc',
                '-i', mermaid_file,
                '-o', output_path,
                '-t', 'default',
                '-b', 'white',
                '-w', '2000',
                '-H', '1080'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return True
            else:
                print(f"Warning: Failed to render Mermaid diagram: {result.stderr}")
                return False
                
        except FileNotFoundError:
            print("Warning: mermaid-cli (mmdc) not found. Please install it with: npm install -g @mermaid-js/mermaid-cli")
            return False
        except Exception as e:
            print(f"Warning: Error rendering Mermaid diagram: {e}")
            return False
    
    def _process_mermaid_diagrams(self, content: str) -> str:
        """Process Mermaid diagrams and replace them with image references"""
        diagrams = self._extract_mermaid_diagrams(content)
        
        for i, (original_block, diagram_code) in enumerate(diagrams):
            png_path = os.path.join(self.temp_dir, f"mermaid_diagram_{i}.png")
            
            if self._render_mermaid_to_png(diagram_code, png_path):
                # Replace the mermaid block with an image reference
                image_ref = f"![Mermaid Diagram {i+1}]({png_path})"
                content = content.replace(original_block, image_ref)
                self.mermaid_images.append(png_path)
            else:
                # If rendering fails, replace with a text note
                content = content.replace(original_block, f"*[Mermaid diagram {i+1} - rendering failed]*")
        
        return content
    
    def _make_urls_clickable(self, content: str) -> str:
        """Convert URLs starting with http or https to clickable links"""
        # Pattern to match URLs starting with http or https, avoiding those in code blocks and quoted strings
        url_pattern = r'(https?://[^\s<>"&]+)(?![^<]*</code>)(?![^<]*</pre>)'
        
        def replace_url(match):
            url = match.group(1)
            # Remove trailing punctuation and HTML entities that might not be part of the URL
            while url and url[-1] in '.,;:!?':
                url = url[:-1]
            # Remove HTML entity endings like &quot;
            if url.endswith('&quot'):
                url = url[:-5]
            if url.endswith('&amp'):
                url = url[:-4]
            if url.endswith('&lt'):
                url = url[:-3]
            if url.endswith('&gt'):
                url = url[:-3]
            return f'<a href="{url}" target="_blank">{url}</a>'
        
        return re.sub(url_pattern, replace_url, content)
    
    def _convert_markdown_to_html(self, content: str) -> str:
        """Convert markdown to HTML with improved code block handling and CRLF support"""
        
        # Use markdown configuration with enhanced code highlighting
        md = markdown.Markdown(
            extensions=[
                'tables',
                'fenced_code',
                'codehilite',
                'nl2br'
            ],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'use_pygments': True,
                    'guess_lang': True,
                    'linenums': False,
                    'noclasses': False,
                    'pygments_style': 'default'
                }
            }
        )
        html_content = md.convert(content)
        
        # Make URLs clickable after markdown conversion
        html_content = self._make_urls_clickable(html_content)
        
        return html_content
    
    def _create_pdf_styles(self):
        """Create PDF styles with improved code formatting"""
        styles = getSampleStyleSheet()
        
        # Enhanced code style with better line breaking
        styles.add(ParagraphStyle(
            name='EnhancedCode',
            parent=styles['Code'],
            fontName='Courier',
            fontSize=8,
            leftIndent=15,
            rightIndent=15,
            backColor=colors.HexColor('#f8f8f8'),
            borderColor=colors.HexColor('#e0e0e0'),
            borderWidth=1,
            borderPadding=6,
            textColor=colors.HexColor('#333333'),
            leading=16,  # Doubled line spacing
            spaceAfter=8,
            spaceBefore=4,
            wordWrap='CJK',  # Enable word wrapping
            splitLongWords=True,  # Break long words
            allowWidows=0,  # Prevent widows
            allowOrphans=0  # Prevent orphans
        ))
        
        # Language label style
        styles.add(ParagraphStyle(
            name='LanguageLabel',
            parent=styles['Heading3'],
            fontSize=10,
            textColor=colors.HexColor('#666666'),
            fontName='Helvetica-Bold',
            spaceAfter=4,
            spaceBefore=8
        ))
        
        return styles

    def _parse_html_to_pdf_elements(self, html_content: str, styles):
        """Parse HTML content and convert to PDF elements using BeautifulSoup"""
        soup = BeautifulSoup(html_content, 'html.parser')
        elements = []
        
        for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'blockquote', 'ul', 'ol', 'li', 'table', 'img', 'a']):
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                text = element.get_text().strip()
                if text:
                    if element.name == 'h1':
                        elements.append(Paragraph(text, styles['Title']))
                    elif element.name == 'h2':
                        elements.append(Paragraph(text, styles['Heading1']))
                    elif element.name == 'h3':
                        elements.append(Paragraph(text, styles['Heading2']))
                    else:
                        elements.append(Paragraph(text, styles['Heading3']))
                    elements.append(Spacer(1, 12))
                    
            elif element.name == 'p':
                text = element.get_text().strip()
                if text:
                    elements.append(Paragraph(text, styles['Normal']))
                    elements.append(Spacer(1, 6))
                    
            elif element.name == 'pre':
                # Handle code blocks with enhanced formatting
                code_element = element.find('code')
                if code_element:
                    # Extract language from class
                    classes = code_element.get('class', [])
                    language = ''
                    if classes:
                        for cls in classes:
                            if cls.startswith('language-'):
                                language = cls.replace('language-', '')
                                break
                    
                    # Get code text and normalize line endings
                    code_text = code_element.get_text()
                    code_text = code_text.replace('\r\n', '\n').replace('\r', '\n')
                    
                    if code_text.strip():
                        # Add language label if available
                        if language:
                            elements.append(Paragraph(f"[{language.upper()}]", styles['LanguageLabel']))
                        
                        # Process code text for better line breaking
                        # processed_code = self._process_code_text(code_text)
                        
                        # Split code into individual lines and create separate paragraphs
                        code_lines = code_text.split('\n')
                        for line in code_lines:
                            if line.strip():  # Only add non-empty lines
                                elements.append(Paragraph(line, styles["EnhancedCode"]))
                            else:  # Add empty line for spacing
                                elements.append(Paragraph("&nbsp;", styles["EnhancedCode"]))
                        elements.append(Spacer(1, 8))
                else:
                    # Plain pre block
                    code_text = element.get_text()
                    code_text = code_text.replace('\r\n', '\n').replace('\r', '\n')
                    
                    if code_text.strip():
                        # Process code text for better line breaking
                        # processed_code = self._process_code_text(code_text)
                        doubled_code_text = code_text
                        elements.append(Paragraph(doubled_code_text, styles["EnhancedCode"]))
                        elements.append(Spacer(1, 8))
                    
            elif element.name == 'code' and element.parent.name != 'pre':
                text = element.get_text().strip()
                if text:
                    # Enhanced inline code formatting
                    elements.append(Paragraph(f"<font name='Courier' color='#d63384'>{text}</font>", styles['Normal']))
                    
            elif element.name == 'blockquote':
                text = element.get_text().strip()
                if text:
                    elements.append(Paragraph(text, styles['Normal']))
                    elements.append(Spacer(1, 8))
                    
            elif element.name in ['ul', 'ol']:
                for li in element.find_all('li'):
                    text = li.get_text().strip()
                    if text:
                        bullet = "• " if element.name == 'ul' else f"{element.find_all('li').index(li) + 1}. "
                        elements.append(Paragraph(f"{bullet}{text}", styles['Normal']))
                elements.append(Spacer(1, 6))
                
            elif element.name == 'table':
                table_data = []
                rows = element.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    row_data = [cell.get_text().strip() for cell in cells]
                    if row_data:
                        table_data.append(row_data)
                
                if table_data:
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    elements.append(table)
                    elements.append(Spacer(1, 12))
                    
            elif element.name == 'a':
                # Handle clickable links with blue color
                href = element.get('href', '')
                text = element.get_text().strip()
                if text and href:
                    # Create a clickable link with blue color in PDF using ReportLab's <a> tag
                    link_text = f'<font color="#0366d6"><a href="{href}">{text}</a></font>'
                    elements.append(Paragraph(link_text, styles['Normal']))
                    elements.append(Spacer(1, 3))
                elif text:
                    # Fallback to blue text if no href
                    elements.append(Paragraph(f'<font color="#0366d6">{text}</font>', styles['Normal']))
                    elements.append(Spacer(1, 3))
                    
            elif element.name == 'img':
                src = element.get('src', '')
                if src and os.path.exists(src):
                    try:
                        # Get original image dimensions to preserve aspect ratio
                        from PIL import Image as PILImage
                        with PILImage.open(src) as pil_img:
                            orig_width, orig_height = pil_img.size
                        
                        # Calculate appropriate size with aspect ratio preservation
                        # Maximum width: 5.5 inches (leaving margin), Maximum height: 7 inches
                        max_width = 5.5 * inch
                        max_height = 7 * inch
                        
                        # Calculate scale factor to fit within constraints
                        width_scale = max_width / orig_width
                        height_scale = max_height / orig_height
                        scale_factor = min(width_scale, height_scale, 1.0)  # Don't upscale
                        
                        # Calculate final dimensions
                        final_width = orig_width * scale_factor
                        final_height = orig_height * scale_factor
                        
                        # Create ReportLab image with proper dimensions
                        img = Image(src, width=final_width, height=final_height)
                        elements.append(img)
                        elements.append(Spacer(1, 6))  # Add some space after image
                    except ImportError:
                        # Fallback if PIL is not available - use conservative sizing
                        try:
                            img = Image(src, width=4*inch)  # Smaller default size
                            img.drawHeight = img.drawWidth * 0.6  # Assume 5:3 aspect ratio
                            elements.append(img)
                            elements.append(Spacer(1, 6))
                        except Exception as e:
                            print(f"Warning: Could not add image {src}: {e}")
                            elements.append(Paragraph(f"[Image: {src}]", styles['Normal']))
                    except Exception as e:
                        print(f"Warning: Could not add image {src}: {e}")
                        elements.append(Paragraph(f"[Image: {src}]", styles['Normal']))

        return elements
    
    def _convert_html_to_pdf(self, html_content: str) -> None:
        """Convert HTML to PDF using ReportLab"""
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                self.output_file,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            styles = self._create_pdf_styles()
            elements = self._parse_html_to_pdf_elements(html_content, styles)
            
            # Build PDF
            doc.build(elements)
            
        except Exception as e:
            print(f"Error converting HTML to PDF: {e}")
            raise
    
    def convert(self):
        """Main conversion method"""
        try:
            # Read markdown file
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"Processing {self.input_file}...")
            
            # Process Mermaid diagrams first
            content = self._process_mermaid_diagrams(content)
            
            # Convert markdown to HTML using GitHub Flavored Markdown
            html_content = self._convert_markdown_to_html(content)
            
            # Generate HTML file name
            html_file = self._generate_html_filename()
            
            # Save HTML file
            self._save_html_file(html_content, html_file)
            print(f"HTML file created: {html_file}")
            
            # Convert HTML to PDF
            self._convert_html_to_pdf(html_content)
            
            print(f"PDF created successfully: {self.output_file}")
            
            # Cleanup temporary files
            for img_path in self.mermaid_images:
                if os.path.exists(img_path):
                    os.remove(img_path)
            
            # Cleanup temporary directory
            try:
                if os.path.exists(self.temp_dir):
                    os.rmdir(self.temp_dir)
            except OSError:
                # Directory not empty, ignore
                pass
                
        except Exception as e:
            print(f"Error converting file: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Markdown files to PDF with Mermaid diagram support"
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
    converter = GitHubMarkdownToPDFConverter(args.file, args.output)
    converter.convert()


if __name__ == "__main__":
    main()