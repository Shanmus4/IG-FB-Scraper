#!/usr/bin/env python3
# facebook_html_builder.py
# Generates a comprehensive HTML report for Facebook data

import os
import json
import base64
from datetime import datetime
from typing import List, Dict, Any

class FacebookHTMLBuilder:
    """Builds an HTML report for Facebook profile data."""
    
    def __init__(self, username: str, profile_data: dict):
        """Initialize with username and profile data."""
        self.username = username
        self.profile_data = profile_data
        self.output_dir = os.path.dirname(os.path.abspath(__file__))
        
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format Unix timestamp to readable date."""
        if not timestamp:
            return ""
        try:
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            return str(timestamp)
    
    def _generate_css(self) -> str:
        """Generate CSS for the HTML report."""
        return """
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #e4e6eb;
                background-color: #18191a;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                display: flex;
                align-items: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 1px solid #3e4042;
            }
            .profile-pic {
                width: 100px;
                height: 100px;
                border-radius: 50%;
                object-fit: cover;
                margin-right: 20px;
                border: 3px solid #2e89ff;
            }
            .profile-info h1 {
                margin: 0 0 10px 0;
                color: #e4e6eb;
            }
            .stats {
                display: flex;
                gap: 20px;
                margin: 10px 0;
            }
            .stat {
                background: #242526;
                padding: 8px 15px;
                border-radius: 8px;
                font-weight: 600;
                color: #b0b3b8;
            }
            .section {
                margin-bottom: 40px;
                background: #242526;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
            .section h2 {
                margin-top: 0;
                color: #e4e6eb;
                border-bottom: 1px solid #3e4042;
                padding-bottom: 10px;
            }
            .posts-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
            }
            .post {
                background: #3a3b3c;
                border-radius: 8px;
                overflow: hidden;
                transition: transform 0.2s;
            }
            .post:hover {
                transform: translateY(-5px);
            }
            .post-image {
                width: 100%;
                height: 300px;
                object-fit: cover;
            }
            .post-content {
                padding: 15px;
            }
            .post-text {
                margin: 10px 0;
                white-space: pre-wrap;
                word-break: break-word;
            }
            .post-meta {
                display: flex;
                justify-content: space-between;
                color: #b0b3b8;
                font-size: 0.9em;
                margin-top: 10px;
            }
            .comments {
                margin-top: 15px;
                border-top: 1px solid #3e4042;
                padding-top: 10px;
            }
            .comment {
                margin-bottom: 10px;
                padding: 8px;
                background: #3a3b3c;
                border-radius: 8px;
            }
            .comment-author {
                font-weight: 600;
                color: #e4e6eb;
                margin-right: 8px;
            }
            .comment-text {
                word-break: break-word;
            }
            .timestamp {
                font-size: 0.8em;
                color: #b0b3b8;
                margin-top: 4px;
            }
            .no-posts {
                text-align: center;
                color: #b0b3b8;
                padding: 40px 0;
            }
            a {
                color: #2e89ff;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            .hidden {
                display: none;
            }
            .toggle-comments {
                background: #3a3b3c;
                border: none;
                color: #b0b3b8;
                padding: 5px 10px;
                border-radius: 4px;
                cursor: pointer;
                margin-top: 10px;
            }
            .toggle-comments:hover {
                background: #4e4f50;
            }
        </style>
        """
    
    def _generate_js(self) -> str:
        """Generate JavaScript for interactive elements."""
        return """
        <script>
            function toggleComments(button) {
                const commentsSection = button.nextElementSibling;
                if (commentsSection.classList.contains('hidden')) {
                    commentsSection.classList.remove('hidden');
                    button.textContent = 'Hide Comments';
                } else {
                    commentsSection.classList.add('hidden');
                    button.textContent = 'Show Comments';
                }
            }
            
            // Expand/collapse long text
            document.addEventListener('DOMContentLoaded', function() {
                const textElements = document.querySelectorAll('.post-text, .comment-text');
                const maxLength = 300;
                
                textElements.forEach(el => {
                    if (el.textContent.length > maxLength) {
                        const fullText = el.textContent;
                        const truncated = fullText.substring(0, maxLength) + '...';
                        const showMore = document.createElement('a');
                        showMore.href = '#';
                        showMore.textContent = 'Show more';
                        showMore.onclick = (e) => {
                            e.preventDefault();
                            el.textContent = fullText;
                        };
                        el.textContent = truncated;
                        el.appendChild(document.createElement('br'));
                        el.appendChild(showMore);
                    }
                });
            });
        </script>
        """
    
    def _generate_post_html(self, post: Dict[str, Any]) -> str:
        """Generate HTML for a single post."""
        post_id = post.get('PostId', '').split('/')[-1] if post.get('PostId') else ''
        post_text = self._escape_html(post.get('Post', ''))
        post_link = post.get('Link', '#')
        post_image = post.get('Image', '')
        post_comments = post.get('Comments', {})
        
        # Format comments
        comments_html = ''
        if post_comments and isinstance(post_comments, dict):
            for author, comment in post_comments.items():
                if isinstance(comment, dict):
                    comment_text = self._escape_html(comment.get('text', ''))
                    comments_html += f'''
                    <div class="comment">
                        <div>
                            <span class="comment-author">{self._escape_html(author)}</span>
                            <span class="comment-text">{comment_text}</span>
                        </div>
                    </div>
                    '''
        
        # Generate post HTML
        post_html = f'''
        <div class="post" id="post-{post_id}">
            {f'<img src="{post_image}" class="post-image" alt="Post image">' if post_image else ''}
            <div class="post-content">
                <div class="post-text">{post_text}</div>
                <div class="post-meta">
                    <a href="{post_link}" target="_blank">View on Facebook</a>
                    <span>{len(post_comments)} comments</span>
                </div>
                {f'<button class="toggle-comments" onclick="toggleComments(this)">Show Comments</button>' if comments_html else ''}
                {f'<div class="comments hidden">{comments_html}</div>' if comments_html else ''}
            </div>
        </div>
        '''
        return post_html
    
    def generate_html(self) -> str:
        """Generate the complete HTML report."""
        posts = self.profile_data.get('posts', [])
        
        # Sort posts by timestamp if available
        if posts and 'timestamp' in posts[0]:
            posts = sorted(posts, key=lambda x: x.get('timestamp', 0), reverse=True)
        
        # Generate posts HTML
        posts_html = ''
        if posts:
            posts_html = '<div class="posts-grid">'
            for post in posts:
                posts_html += self._generate_post_html(post)
            posts_html += '</div>'
        else:
            posts_html = '<div class="no-posts">No posts found.</div>'
        
        # Generate the complete HTML
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Facebook Profile: {username}</title>
            {css}
        </head>
        <body>
            <div class="header">
                <img src="{profile_pic}" class="profile-pic" alt="Profile picture">
                <div class="profile-info">
                    <h1>{name}</h1>
                    <div class="stats">
                        <div class="stat">{post_count} Posts</div>
                        <div class="stat">{follower_count} Followers</div>
                        <div class="stat">{following_count} Following</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>About</h2>
                <div class="about">
                    {about}
                </div>
            </div>
            
            <div class="section">
                <h2>Posts</h2>
                {posts_html}
            </div>
            
            {js}
        </body>
        </html>
        """.format(
            username=self._escape_html(self.username),
            name=self._escape_html(self.profile_data.get('name', '')),
            profile_pic=self.profile_data.get('profile_picture', ''),
            post_count=len(posts),
            follower_count=self.profile_data.get('follower_count', 0),
            following_count=self.profile_data.get('following_count', 0),
            about=self._escape_html(self.profile_data.get('about', '')),
            posts_html=posts_html,
            css=self._generate_css(),
            js=self._generate_js()
        )
        
        return html
    
    def save_html(self, output_path: str = None) -> str:
        """Save the HTML report to a file."""
        if not output_path:
            output_path = os.path.join(self.output_dir, f"{self.username}_facebook_report.html")
        
        html_content = self.generate_html()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path

def main():
    """Example usage."""
    # Example data structure
    profile_data = {
        'name': 'John Doe',
        'profile_picture': '',
        'follower_count': 1000,
        'following_count': 500,
        'about': 'This is a sample Facebook profile.',
        'posts': [
            {
                'PostId': '12345',
                'Post': 'This is a sample Facebook post with some text.',
                'Link': 'https://facebook.com/12345',
                'Image': 'https://example.com/image.jpg',
                'Comments': {
                    'user1': {'text': 'Nice post!'},
                    'user2': {'text': 'Thanks for sharing!'}
                }
            },
            # Add more posts as needed
        ]
    }
    
    builder = FacebookHTMLBuilder('johndoe', profile_data)
    output_path = builder.save_html()
    print(f"HTML report saved to: {output_path}")

if __name__ == "__main__":
    main()
