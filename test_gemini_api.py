#!/usr/bin/env python3
"""
Test script for Gemini API calls.

Tests both models:
1. gemini-robotics-er-1.5-preview (for planning)
2. gemini-3-flash-preview (for task detection)
"""

import os
import sys
from dotenv import load_dotenv
import numpy as np
from PIL import Image
import io
import cv2

# Load environment variables
load_dotenv()

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("Error: google-genai package not installed")
    print("Install with: pip install google-genai")
    sys.exit(1)


def load_test_image():
    """Load test image from snapshot.jpg, or create a simple one if not found."""
    snapshot_path = "snapshot.jpg"
    if os.path.exists(snapshot_path):
        # Load existing snapshot
        image = cv2.imread(snapshot_path)
        if image is not None:
            print(f"✓ Loaded test image from {snapshot_path} ({image.shape[1]}x{image.shape[0]})")
            return image
        else:
            print(f"⚠️  Warning: Could not load {snapshot_path}, creating test image")
    else:
        print(f"⚠️  Warning: {snapshot_path} not found, creating test image")
    
    # Fallback: Create a simple test image
    width, height = 640, 480
    image = np.zeros((height, width, 3), dtype=np.uint8)
    # Add some colored rectangles
    cv2.rectangle(image, (100, 100), (300, 200), (0, 0, 255), -1)  # Red rectangle
    cv2.rectangle(image, (350, 150), (550, 250), (0, 255, 0), -1)  # Green rectangle
    cv2.putText(image, "Test Image", (200, 400), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return image


def image_to_bytes(image: np.ndarray) -> bytes:
    """Convert numpy image to JPEG bytes."""
    if len(image.shape) == 3 and image.shape[2] == 3:
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    else:
        image_rgb = image
    
    pil_image = Image.fromarray(image_rgb)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def test_robotics_er_model():
    """Test gemini-robotics-er-1.5-preview model."""
    print("\n" + "="*60)
    print("Testing: gemini-robotics-er-1.5-preview (Planning Model)")
    print("="*60)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not set in .env file")
        return False
    
    try:
        # Initialize client with longer timeout
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
        )
        
        model_name = "gemini-robotics-er-1.5-preview"
        print(f"✓ Client initialized")
        print(f"✓ Model: {model_name}")
        
        # Test 1: Simple text-only request (faster)
        print("\n[Test 1] Text-only request...")
        prompt = "Say 'Hello, I am a robot planning system' in one sentence."
        
        parts = [genai_types.Part.from_text(text=prompt)]
        contents = [genai_types.Content(parts=parts)]
        
        # Set deadline in httpOptions (minimum 10 seconds)
        config = genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=100,
            httpOptions=genai_types.HttpOptions(timeout=120000)  # 120 seconds in milliseconds
        )
        
        print("📤 Sending text request...")
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        
        response_text = ""
        if hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                parts = candidate.content.parts
                for part in parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
        
        print(f"✓ Text request successful!")
        print(f"📥 Response: {response_text[:150]}")
        
        # Test 2: Image + text request
        print("\n[Test 2] Image + text request...")
        test_image = load_test_image()
        image_bytes = image_to_bytes(test_image)
        
        prompt = "Describe what you see in this image in one sentence."
        
        parts = [
            genai_types.Part.from_text(text=prompt),
            genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        ]
        contents = [genai_types.Content(parts=parts)]
        
        print("📤 Sending image request...")
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        
        response_text = ""
        if hasattr(response, 'text') and response.text:
            response_text = response.text
        elif hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                parts = candidate.content.parts
                if parts:
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
        
        print(f"✓ Image request successful!")
        if response_text:
            print(f"📥 Response: {response_text[:150]}")
        else:
            print(f"📥 Response: (empty or no text)")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            print(f"⚠️  Timeout: API call took too long (this may be a network issue)")
            print(f"   The model may still be working, but the connection timed out")
        else:
            print(f"❌ Error: {error_msg}")
            import traceback
            traceback.print_exc()
        return False


def test_flash_model():
    """Test gemini-3-flash-preview model."""
    print("\n" + "="*60)
    print("Testing: gemini-3-flash-preview (Task Detection Model)")
    print("="*60)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not set in .env file")
        return False
    
    try:
        # Initialize client with longer timeout
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
        )
        
        model_name = "gemini-3-flash-preview"
        print(f"✓ Client initialized")
        print(f"✓ Model: {model_name}")
        
        # Load test image once for both tests
        test_image = load_test_image()
        image_bytes = image_to_bytes(test_image)
        
        # Test 1: Simple text-only request (faster)
        print("\n[Test 1] Text-only request...")
        prompt_text = "Say 'Hello, I am a task detection system' in one sentence."
        
        parts_text = [genai_types.Part.from_text(text=prompt_text)]
        contents_text = [genai_types.Content(parts=parts_text)]
        
        config_text = genai_types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=100,
            httpOptions=genai_types.HttpOptions(timeout=120000)  # 120 seconds in milliseconds
        )
        
        print("📤 Sending text request...")
        response = client.models.generate_content(
            model=model_name,
            contents=contents_text,
            config=config_text
        )
        
        response_text = ""
        if hasattr(response, 'text') and response.text:
            response_text = response.text
        elif hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                parts = candidate.content.parts
                if parts:
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
        
        print(f"✓ Text request successful!")
        if response_text:
            print(f"📥 Response: {response_text[:150]}")
        else:
            print(f"📥 Response: (empty or no text)")
        
        # Test 2: Image + JSON response
        print("\n[Test 2] Image + JSON response request...")
        
        # Build prompt for task completion check
        prompt = """You are a task completion checker for a robot.

Current task: pick up red block

Look at the image and determine if the task has been completed. 

Return your answer in this exact JSON format:
{
    "completed": true or false,
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation",
    "evidence": "what you see in the image that supports your conclusion"
}"""
        
        # Prepare contents with image
        parts = [
            genai_types.Part.from_text(text=prompt),
            genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        ]
        contents = [genai_types.Content(parts=parts)]
        
        # Build config for JSON response with httpOptions
        config = genai_types.GenerateContentConfig(
            temperature=0.1,
            responseMimeType="application/json",
            httpOptions=genai_types.HttpOptions(timeout=120000)  # 120 seconds in milliseconds
        )
        
        # Prepare contents with image
        parts = [
            genai_types.Part.from_text(text=prompt),
            genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        ]
        contents = [genai_types.Content(parts=parts)]
        
        print("📤 Sending image request...")
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        
        response_text = ""
        if hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                parts = candidate.content.parts
                for part in parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
        
        print(f"✓ Image request successful!")
        print(f"📥 Response: {response_text[:300]}...")
        
        # Try to parse JSON
        import json
        try:
            response_text_clean = response_text.strip()
            if response_text_clean.startswith("```json"):
                response_text_clean = response_text_clean[7:]
            if response_text_clean.startswith("```"):
                response_text_clean = response_text_clean[3:]
            if response_text_clean.endswith("```"):
                response_text_clean = response_text_clean[:-3]
            response_text_clean = response_text_clean.strip()
            
            result = json.loads(response_text_clean)
            print(f"✓ JSON parsed successfully:")
            print(f"  - completed: {result.get('completed')}")
            print(f"  - confidence: {result.get('confidence')}")
            print(f"  - reason: {result.get('reason', '')[:100]}")
        except json.JSONDecodeError:
            print(f"⚠️  Warning: Could not parse JSON response")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            print(f"⚠️  Timeout: API call took too long (this may be a network issue)")
            print(f"   The model may still be working, but the connection timed out")
        else:
            print(f"❌ Error: {error_msg}")
            import traceback
            traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Gemini API Test Script")
    print("="*60)
    
    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n❌ Error: GEMINI_API_KEY not found in environment")
        print("   Please set it in your .env file")
        sys.exit(1)
    
    print(f"✓ GEMINI_API_KEY found (length: {len(api_key)})")
    print(f"✓ API key starts with: {api_key[:10]}...")
    print(f"\n⚠️  Note: API calls may take 30-120 seconds depending on network speed")
    print(f"   Timeout is set to 120 seconds\n")
    
    # Test both models
    results = []
    
    # Test 1: Robotics ER model
    result1 = test_robotics_er_model()
    results.append(("gemini-robotics-er-1.5-preview", result1))
    
    # Test 2: Flash model
    result2 = test_flash_model()
    results.append(("gemini-3-flash-preview", result2))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for model_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {model_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

