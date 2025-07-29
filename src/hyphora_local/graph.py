import re


def extract_wiki_links(content: str) -> list[str]:
    """Extract wiki-style links from markdown content.

    Supports formats like:
    - [[Link Text]]
    - [[Link Text|Display Text]]
    - [[Link Text#Section]]
    """
    # Pattern to match [[link]] or [[link|display]] or [[link#section]]
    pattern = r"\[\[([^\]]+)\]\]"
    matches = re.findall(pattern, content)

    links: list[str] = []
    for match in matches:
        # Handle [[link|display]] format
        if "|" in match:
            link = match.split("|")[0].strip()
        else:
            link = match.strip()

        # Remove section anchors if present
        if "#" in link:
            link = link.split("#")[0].strip()

        links.append(link)

    return links
