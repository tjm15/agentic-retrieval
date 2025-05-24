#!/usr/bin/env python3
"""
Simple validation script for the enhanced LLM abstraction layer.
"""

import os
import sys

def validate_imports():
    """Validate that all modules can be imported"""
    print("🔍 Validating Enhanced LLM Imports...")
    
    try:
        # Test standard library imports
        import asyncio
        import logging
        from enum import Enum
        from dataclasses import dataclass
        print("✅ Standard library imports successful")
        
        # Test existing project imports
        from config import create_llm_client
        print("✅ Existing LLM client import successful")
        
        # Test enhanced module imports
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        from enhanced_llm_client import LLMResponse, LLMMetrics
        print("✅ Enhanced LLM client base classes imported")
        
        from enhanced_providers import EnhancedGeminiClient, EnhancedOpenRouterClient
        print("✅ Enhanced provider classes imported")
        
        from enhanced_fallback_client import EnhancedFallbackLLMClient
        print("✅ Enhanced fallback client imported")
        
        from enhanced_config import create_enhanced_llm_client, validate_llm_configuration
        print("✅ Enhanced config functions imported")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def validate_configuration():
    """Validate LLM configuration"""
    print("\n🔍 Validating LLM Configuration...")
    
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    print(f"  GEMINI_API_KEY: {'✅ Set' if gemini_key else '❌ Not set'}")
    print(f"  OPENROUTER_API_KEY: {'✅ Set' if openrouter_key else '❌ Not set'}")
    
    if not gemini_key and not openrouter_key:
        print("⚠️  No API keys configured. Enhanced client will not be fully functional.")
        return False
    
    return True

def main():
    """Main validation function"""
    print("Enhanced LLM Abstraction Layer Validation")
    print("=" * 50)
    
    imports_ok = validate_imports()
    config_ok = validate_configuration()
    
    print("\n" + "=" * 50)
    if imports_ok and config_ok:
        print("🎉 Validation successful! Enhanced LLM abstraction layer is ready.")
        return 0
    elif imports_ok:
        print("⚠️  Imports successful but configuration incomplete.")
        print("   Set GEMINI_API_KEY and/or OPENROUTER_API_KEY to enable full functionality.")
        return 1
    else:
        print("❌ Validation failed. Check imports and dependencies.")
        return 2

if __name__ == "__main__":
    sys.exit(main())
