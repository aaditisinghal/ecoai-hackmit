#!/usr/bin/env python3
"""
Test the EcoAI Flask Portal
"""

import requests
import json
import time
from datetime import datetime

class EcoAIPortalTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.api_key = None
        
    def test_homepage(self):
        """Test the homepage"""
        print("🏠 Testing Homepage...")
        try:
            response = self.session.get(f"{self.base_url}/")
            if response.status_code == 200:
                print("✅ Homepage loads successfully")
                return True
            else:
                print(f"❌ Homepage failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Homepage error: {e}")
            return False
    
    def test_signup(self):
        """Test user signup"""
        print("📝 Testing User Signup...")
        try:
            signup_data = {
                "username": f"testuser_{int(time.time())}",
                "email": f"test_{int(time.time())}@example.com",
                "password": "testpassword123",
                "confirm_password": "testpassword123"
            }
            
            response = self.session.post(f"{self.base_url}/signup", data=signup_data)
            if response.status_code == 302:  # Redirect after successful signup
                print("✅ User signup successful")
                # Extract API key from flash message (simulated)
                self.api_key = f"ecoai_test_{int(time.time())}"
                return True
            else:
                print(f"❌ Signup failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Signup error: {e}")
            return False
    
    def test_login(self):
        """Test user login"""
        print("🔐 Testing User Login...")
        try:
            login_data = {
                "username": "testuser",
                "password": "testpassword123"
            }
            
            response = self.session.post(f"{self.base_url}/login", data=login_data)
            if response.status_code == 302:  # Redirect after successful login
                print("✅ User login successful")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def test_dashboard(self):
        """Test dashboard access"""
        print("📊 Testing Dashboard...")
        try:
            response = self.session.get(f"{self.base_url}/dashboard")
            if response.status_code == 200:
                print("✅ Dashboard loads successfully")
                return True
            else:
                print(f"❌ Dashboard failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Dashboard error: {e}")
            return False
    
    def test_api_ingest(self):
        """Test API data ingestion"""
        print("📡 Testing API Data Ingestion...")
        try:
            if not self.api_key:
                self.api_key = "ecoai_test_api_key"
            
            test_receipt = {
                "receipt_id": f"test_receipt_{int(time.time())}",
                "tokens_before": 100,
                "tokens_after": 80,
                "kwh_before": 0.001,
                "kwh_after": 0.0008,
                "co2_g_before": 0.00035,
                "co2_g_after": 0.00028,
                "quality_score": 0.95,
                "route": {
                    "model": "gpt-4o-mini",
                    "region": "us-west-2"
                },
                "optimizations_applied": ["Removed 'please'", "Removed 'kindly'"]
            }
            
            headers = {"X-API-Key": self.api_key}
            data = {"events": [{"type": "receipt", "receipt_id": test_receipt["receipt_id"], "payload": test_receipt}]}
            
            response = requests.post(f"{self.base_url}/api/ingest/batch", 
                                   headers=headers, json=data)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Data ingestion successful: {result}")
                return True
            else:
                print(f"❌ Data ingestion failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Data ingestion error: {e}")
            return False
    
    def test_api_metrics(self):
        """Test API metrics endpoints"""
        print("📈 Testing API Metrics...")
        try:
            if not self.api_key:
                self.api_key = "ecoai_test_api_key"
            
            headers = {"X-API-Key": self.api_key}
            
            # Test summary metrics
            response = requests.get(f"{self.base_url}/api/metrics/summary", headers=headers)
            if response.status_code == 200:
                print("✅ Metrics summary endpoint working")
            else:
                print(f"❌ Metrics summary failed: {response.status_code}")
                return False
            
            # Test timeseries metrics
            response = requests.get(f"{self.base_url}/api/metrics/timeseries", headers=headers)
            if response.status_code == 200:
                print("✅ Metrics timeseries endpoint working")
            else:
                print(f"❌ Metrics timeseries failed: {response.status_code}")
                return False
            
            # Test receipts endpoint
            response = requests.get(f"{self.base_url}/api/receipts", headers=headers)
            if response.status_code == 200:
                print("✅ Receipts endpoint working")
                return True
            else:
                print(f"❌ Receipts endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ API metrics error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("🧪 ECOAI FLASK PORTAL TEST SUITE")
        print("=" * 50)
        
        tests = [
            ("Homepage", self.test_homepage),
            ("Signup", self.test_signup),
            ("Login", self.test_login),
            ("Dashboard", self.test_dashboard),
            ("API Ingest", self.test_api_ingest),
            ("API Metrics", self.test_api_metrics)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                print()
            except Exception as e:
                print(f"❌ {test_name} crashed: {e}")
                results.append((test_name, False))
                print()
        
        # Summary
        print("📋 TEST SUMMARY")
        print("=" * 50)
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Portal is working perfectly!")
        elif passed >= total * 0.8:
            print("✅ Most tests passed. Portal is mostly working!")
        else:
            print("⚠️ Several tests failed. Portal needs attention.")

def main():
    """Run the portal tests"""
    print("Starting EcoAI Flask Portal Tests...")
    print("Make sure the Flask app is running on http://localhost:8000")
    print()
    
    tester = EcoAIPortalTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
