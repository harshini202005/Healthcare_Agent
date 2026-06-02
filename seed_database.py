#!/usr/bin/env python3
"""
Database Seeding Script for Healthcare MCP Server
Run this after setting up Supabase tables to populate initial data
"""

import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database import get_db

load_dotenv()


def seed_all():
    """Seed all database tables with initial data"""
    print("=" * 60)
    print("🏥 Healthcare MCP Server - Database Seeder")
    print("=" * 60)
    
    db = get_db()
    
    try:
        # Seed doctors
        print("\n📋 Step 1: Seeding doctors...")
        doctor_count = db.seed_doctors()
        print(f"   ✅ Seeded {doctor_count} doctors")
        
        # Seed schedules
        print("\n📅 Step 2: Seeding doctor schedules...")
        schedule_count = db.seed_schedules()
        print(f"   ✅ Seeded {schedule_count} schedules")
        
        print("\n" + "=" * 60)
        print("✨ Database seeding complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start the server: ./start.sh")
        print("2. Test the API at: http://localhost:8000/mcp/tools")
        print("3. Try booking: POST /mcp/call with book_appointment")
        
    except Exception as e:
        print(f"\n❌ Seeding failed: {e}")
        print("\nTroubleshooting:")
        print("- Verify SUPABASE_URL and SUPABASE_KEY in .env")
        print("- Ensure you've run supabase_schema.sql in Supabase SQL Editor")
        sys.exit(1)


def verify_connection():
    """Verify database connection works"""
    print("\n🔌 Testing database connection...")
    try:
        db = get_db()
        # Try a simple query
        response = db.client.table("doctors").select("count", count="exact").execute()
        print("   ✅ Connection successful!")
        return True
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("\nChecking environment...")
    
    # Check env vars
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("\n❌ Missing environment variables!")
        print("Add to your .env file:")
        print("  SUPABASE_URL=https://your-project.supabase.co")
        print("  SUPABASE_KEY=your-anon-key")
        print("\nGet these from: https://supabase.com/dashboard/project/_/settings/api")
        sys.exit(1)
    
    if verify_connection():
        seed_all()
    else:
        print("\nPlease check your Supabase credentials and try again.")
        sys.exit(1)