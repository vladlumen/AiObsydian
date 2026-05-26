from src.cognitive.llm_service import llm
from pathlib import Path

class VisionService:
    def __init__(self):
        pass
    
    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using vision model and return extracted text."""
        # Use the LLM service's analyze_image method with vision model
        return await llm.analyze_image(
            image_path=image_path,
            prompt=prompt,
            system_prompt="",  # No system prompt needed for basic OCR
            model_name="llama3.2-vision"
        )

vision_service = VisionService()