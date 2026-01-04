#!/usr/bin/env python3
"""
RPC Server Test Script for MasterPi Robot
Tests and detects available RPC server functions.
"""

import sys
import argparse
import xmlrpc.client
import json
import requests
import socket
import time
import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def detect_protocol(ip_address: str, port: int, timeout: int = 10) -> str:
    """
    Detect which RPC protocol the server uses by making a test request.
    
    Args:
        ip_address: IP address of the robot
        port: Port number for RPC server
        timeout: Connection timeout in seconds
    
    Returns:
        'jsonrpc', 'xmlrpc', or 'unknown'
    """
    rpc_url = f"http://{ip_address}:{port}/"
    
    try:
        # Make a simple test request to see what format the server returns
        test_payload = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": [],
            "id": 1
        }
        
        response = requests.post(
            rpc_url,
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        
        if response.status_code == 200:
            # Check if response is JSON
            try:
                result = response.json()
                if isinstance(result, dict) and ("jsonrpc" in result or "result" in result or "error" in result):
                    return "jsonrpc"
            except:
                pass
            
            # Check if response is XML
            content = response.text.strip()
            if content.startswith("<?xml") or content.startswith("<methodResponse"):
                return "xmlrpc"
        
        # Check Content-Type header
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            return "jsonrpc"
        elif "application/xml" in content_type or "text/xml" in content_type:
            return "xmlrpc"
            
    except Exception:
        pass
    
    return "unknown"


def test_xmlrpc(ip_address: str, port: int, timeout: int = 10) -> Optional[xmlrpc.client.ServerProxy]:
    """
    Test XML-RPC connection and return server proxy if successful.
    
    Args:
        ip_address: IP address of the robot
        port: Port number for RPC server
        timeout: Connection timeout in seconds
    
    Returns:
        ServerProxy if successful, None otherwise
    """
    rpc_url = f"http://{ip_address}:{port}/"
    
    try:
        print(f"Attempting XML-RPC connection to {rpc_url}...")
        
        # Set socket timeout for compatibility with older Python versions
        # ServerProxy timeout parameter is only available in Python 3.5+
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        
        try:
            # Try without timeout first (for older Python versions)
            try:
                proxy = xmlrpc.client.ServerProxy(rpc_url)
            except TypeError:
                # If that fails, try with timeout (Python 3.5+)
                proxy = xmlrpc.client.ServerProxy(rpc_url, timeout=timeout)
            
            # Try to get system methods (introspection)
            try:
                methods = proxy.system.listMethods()
                print(f"✓ XML-RPC connection successful!")
                print(f"  Found {len(methods)} available methods")
                socket.setdefaulttimeout(old_timeout)
                return proxy
            except Exception as e:
                # Check if error indicates JSON response (not XML)
                error_str = str(e).lower()
                if "not well-formed" in error_str or "invalid token" in error_str:
                    # This likely means server is returning JSON, not XML
                    socket.setdefaulttimeout(old_timeout)
                    return None
                # Some servers don't support introspection, but connection might still work
                print(f"✓ XML-RPC connection successful (introspection not available: {e})")
                socket.setdefaulttimeout(old_timeout)
                return proxy
        finally:
            socket.setdefaulttimeout(old_timeout)
            
    except Exception as e:
        # Check if error indicates JSON response (not XML)
        error_str = str(e).lower()
        if "not well-formed" in error_str or "invalid token" in error_str:
            print(f"✗ Server appears to be using JSON-RPC, not XML-RPC")
        else:
            print(f"✗ XML-RPC connection failed: {e}")
        return None


def test_jsonrpc(ip_address: str, port: int, timeout: int = 10) -> bool:
    """
    Test JSON-RPC connection.
    
    Args:
        ip_address: IP address of the robot
        port: Port number for RPC server
        timeout: Connection timeout in seconds
    
    Returns:
        True if JSON-RPC is available, False otherwise
    """
    rpc_url = f"http://{ip_address}:{port}/"
    
    try:
        print(f"Attempting JSON-RPC connection to {rpc_url}...")
        
        # Try a simple JSON-RPC 2.0 call with a common method
        # First try system.listMethods, if that fails, try a simple ping
        test_methods = ["system.listMethods", "ping", "status"]
        
        for method_name in test_methods:
            payload = {
                "jsonrpc": "2.0",
                "method": method_name,
                "params": [],
                "id": 1
            }
            
            try:
                response = requests.post(
                    rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        print(f"✓ JSON-RPC connection successful!")
                        print(f"  Tested method '{method_name}': {result.get('result', 'OK')}")
                        return True
                    elif "error" in result:
                        # Method not found is OK - it means the server is responding
                        if result["error"].get("code") == -32601:  # Method not found
                            print(f"✓ JSON-RPC server is responding (method '{method_name}' not found)")
                            print(f"  This indicates JSON-RPC is available, but method names are needed")
                            return True
                        else:
                            print(f"  JSON-RPC error for '{method_name}': {result['error']}")
                            continue
            except requests.exceptions.RequestException as e:
                print(f"✗ JSON-RPC connection failed: {e}")
                return False
        
        return False
        
    except Exception as e:
        print(f"✗ JSON-RPC connection failed: {e}")
        return False


def list_methods(proxy: xmlrpc.client.ServerProxy) -> List[str]:
    """
    List all available RPC methods.
    
    Args:
        proxy: XML-RPC ServerProxy
    
    Returns:
        List of method names
    """
    try:
        methods = proxy.system.listMethods()
        # Filter out system methods if desired
        user_methods = [m for m in methods if not m.startswith("system.")]
        return methods, user_methods
    except Exception as e:
        print(f"Warning: Could not list methods: {e}")
        return [], []


def get_method_signature(proxy: xmlrpc.client.ServerProxy, method_name: str) -> Optional[str]:
    """
    Get method signature/help text.
    
    Args:
        proxy: XML-RPC ServerProxy
        method_name: Name of the method
    
    Returns:
        Method signature/help text or None
    """
    try:
        signature = proxy.system.methodSignature(method_name)
        return signature
    except:
        try:
            help_text = proxy.system.methodHelp(method_name)
            return help_text
        except:
            return None


def call_jsonrpc_method(ip_address: str, port: int, method_name: str, params: list = None, timeout: int = 10) -> Dict[str, Any]:
    """
    Call a JSON-RPC method on the server.
    
    Args:
        ip_address: IP address of the robot
        port: Port number for RPC server
        method_name: Name of the method to call
        params: Parameters for the method (default: [])
        timeout: Connection timeout in seconds
    
    Returns:
        Dictionary with 'success', 'result', and 'error' keys
    """
    rpc_url = f"http://{ip_address}:{port}/"
    
    if params is None:
        params = []
    
    payload = {
        "jsonrpc": "2.0",
        "method": method_name,
        "params": params,
        "id": 1
    }
    
    try:
        response = requests.post(
            rpc_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                return {
                    "success": True,
                    "result": result["result"],
                    "error": None
                }
            elif "error" in result:
                return {
                    "success": False,
                    "result": None,
                    "error": result["error"]
                }
        else:
            return {
                "success": False,
                "result": None,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "result": None,
            "error": str(e)
        }


def test_level1_functions(ip_address: str, port: int, timeout: int = 10) -> Dict[str, Any]:
    """
    Test Level 1 (high-level) functions from MasterPi RPC server.
    Based on: https://github.com/zhaozhichen/masterpi/blob/master/RPCServer_%E5%8A%9F%E8%83%BD%E5%88%97%E8%A1%A8.md
    
    Args:
        ip_address: IP address of the robot
        port: Port number for RPC server
        timeout: Connection timeout in seconds
    
    Returns:
        Dictionary of test results
    """
    TEST_SPEED = 50  # 使用整数，范围 -100 到 100
    # Level 1 functions organized by category
    level1_functions_by_category = {
        "停止运动": [
            ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        ],
        "传感器读取": [
            ("GetBatteryVoltage", []),
        ],
        "夹持器操作": [
            ("SetGripperOpen", []),
            ("SetGripperClose", []),
        ],
        "机械臂高级操作": [
            # ArmMoveIk(x, y, z, pitch, roll, yaw, speed)
            # Initial position
            ("ArmMoveIk", [0.0, 5.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            # X range
            ("ArmMoveIk", [-15.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [-10.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [-5.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [5.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [10.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [15.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            # Y range
            ("ArmMoveIk", [0.0, 0.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 5.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 15.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 20.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            # Z range
            ("ArmMoveIk", [0.0, 10.0, -5.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 0.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 5.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 10.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 20.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            ("ArmMoveIk", [0.0, 10.0, 25.0, 0.0, -90.0, 90.0, 1500], {"optional": True, "note": "Initial position"}),
            # StopBusServo 需要字符串参数 "stopAction"
            ("StopBusServo", ["stopAction"]),
        ],
        # "Mecanum底盘高级操作": [
        #     # SetMecanumVelocity(velocity, direction, angular_rate)
        #     # 根据文档：velocity(0-200 mm/s建议), direction(0-360度), angular_rate(度/秒,建议不超过50)
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [TEST_SPEED, 0.0, 0.0], {"note": "Forward movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [TEST_SPEED, 45.0, 0.0], {"note": "Right-forward movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [-1*TEST_SPEED, 90.0, 0.0], {"note": "Left movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [TEST_SPEED, 180.0, 0.0], {"note": "Backward movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 30.0], {"note": "Rotate in place"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [TEST_SPEED, 0.0, 20.0], {"note": "Move forward with rotation"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [1.5*TEST_SPEED, 0.0, 0.0], {"note": "High speed movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [0.2*TEST_SPEED, 0.0, 0.0], {"note": "Slow speed movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Stop movement"}),
        #     ("SetMecanumVelocity", [TEST_SPEED, 270.0, 0.0], {"note": "Right movement"}),
        #     ("SetMecanumVelocity", [0.0, 0.0, 0.0], {"note": "Final stop"}),
        # ],
        # "电机底层控制（轮子测试）": [
        #     # SetBrushMotor(motor_id, speed, ...)
        #     # 根据文档：motor_id范围1-4（对应4个轮子），speed范围-100到100
        #     # 测试用例1：停止所有轮子
        #     ("SetBrushMotor", [1, 0, 2, 0, 3, 0, 4, 0], {"note": "Stop all motors"}),
        #     # 测试用例2：测试轮子1（正转）
        #     ("SetBrushMotor", [1, TEST_SPEED], {"note": "Motor 1 forward"}),
        #     # 测试用例3：停止轮子1
        #     ("SetBrushMotor", [1, 0], {"note": "Stop motor 1"}),
        #     # 测试用例4：测试轮子2（正转）
        #     ("SetBrushMotor", [2, TEST_SPEED], {"note": "Motor 2 forward"}),
        #     # 测试用例5：停止轮子2
        #     ("SetBrushMotor", [2, 0], {"note": "Stop motor 2"}),
        #     # 测试用例6：测试轮子3（正转）
        #     ("SetBrushMotor", [3, TEST_SPEED], {"note": "Motor 3 forward"}),
        #     # 测试用例7：停止轮子3
        #     ("SetBrushMotor", [3, 0], {"note": "Stop motor 3"}),
        #     # 测试用例8：测试轮子4（正转）
        #     ("SetBrushMotor", [4, TEST_SPEED], {"note": "Motor 4 forward"}),
        #     # 测试用例9：停止轮子4
        #     ("SetBrushMotor", [4, 0], {"note": "Stop motor 4"}),
        #     # 测试用例10：测试轮子1（反转）
        #     ("SetBrushMotor", [1, -1*TEST_SPEED], {"note": "Motor 1 reverse"}),
        #     # 测试用例11：停止轮子1
        #     ("SetBrushMotor", [1, 0], {"note": "Stop motor 1"}),
        #     # 测试用例12：测试轮子2（反转）
        #     ("SetBrushMotor", [2, -1*TEST_SPEED], {"note": "Motor 2 reverse"}),
        #     # 测试用例13：停止轮子2
        #     ("SetBrushMotor", [2, 0], {"note": "Stop motor 2"}),
        #     # 测试用例14：测试轮子3（反转）
        #     ("SetBrushMotor", [3, -1*TEST_SPEED], {"note": "Motor 3 reverse"}),
        #     # 测试用例15：停止轮子3
        #     ("SetBrushMotor", [3, 0], {"note": "Stop motor 3"}),
        #     # 测试用例16：测试轮子4（反转）
        #     ("SetBrushMotor", [4, -1*TEST_SPEED], {"note": "Motor 4 reverse"}),
        #     # 测试用例17：停止轮子4
        #     ("SetBrushMotor", [4, 0], {"note": "Stop motor 4"}),
        #     # 测试用例18：测试不同速度（轮子1，低速）
        #     ("SetBrushMotor", [1, int(0.3*TEST_SPEED)], {"note": "Motor 1 low speed"}),
        #     # 测试用例19：停止
        #     ("SetBrushMotor", [1, 0], {"note": "Stop motor 1"}),
        #     # 测试用例20：测试不同速度（轮子1，中速）
        #     ("SetBrushMotor", [1, TEST_SPEED], {"note": "Motor 1 medium speed"}),
        #     # 测试用例21：停止
        #     ("SetBrushMotor", [1, 0], {"note": "Stop motor 1"}),
        #     # 测试用例22：测试不同速度（轮子1，高速，但不超过100）
        #     ("SetBrushMotor", [1, min(80, int(1.5*TEST_SPEED))], {"note": "Motor 1 high speed"}),
        #     # 测试用例23：停止
        #     ("SetBrushMotor", [1, 0], {"note": "Stop motor 1"}),
        #     # 测试用例24：同时测试两个轮子（1和2）
        #     ("SetBrushMotor", [1, TEST_SPEED, 2, TEST_SPEED], {"note": "Motors 1&2 forward"}),
        #     # 测试用例25：停止
        #     ("SetBrushMotor", [1, 0, 2, 0], {"note": "Stop motors 1&2"}),
        #     # 测试用例26：同时测试所有轮子（正转）
        #     ("SetBrushMotor", [1, TEST_SPEED, 2, TEST_SPEED, 3, TEST_SPEED, 4, TEST_SPEED], {"note": "All motors forward"}),
        #     # 测试用例27：停止所有轮子
        #     ("SetBrushMotor", [1, 0, 2, 0, 3, 0, 4, 0], {"note": "Stop all motors"}),
        # ],
    }
    
    # Flatten the function list and handle optional metadata
    all_functions = []
    for category, functions in level1_functions_by_category.items():
        for func in functions:
            if len(func) == 3:  # Has metadata
                all_functions.append((func[0], func[1], func[2]))
            else:  # No metadata
                all_functions.append((func[0], func[1], {}))
    
    print("Testing Level 1 Functions (High-Level Functions)")
    print("=" * 60)
    print("\n⚠️  WARNING: This test includes movement functions!")
    print("   The robot may move during testing.")
    print("   Make sure the robot has enough space and is ready for movement.")
    
    # Count total test cases
    total_cases = sum(len(funcs) for funcs in level1_functions_by_category.values())
    print(f"\nTotal test cases: {total_cases}")
    print("  - SetMecanumVelocity: 2 test cases (stop movement)")
    print("  - SetBrushMotor: 27 test cases (individual wheel testing)")
    print("    * Each wheel (1-4) tested separately (forward and reverse)")
    print("    * Different speeds tested (low, medium, high)")
    print("    * Multiple wheels tested together")
    print("-" * 60)
    
    results = {}
    success_count = 0
    fail_count = 0
    category_results = {}
    
    # Test each function
    for func_item in all_functions:
        if len(func_item) == 3:
            method_name, params, metadata = func_item
        else:
            method_name, params = func_item
            metadata = {}
        
        # Add delay between tests to allow robot to complete movements
        # Longer delay for movement functions
        if method_name in ["ArmMoveIk", "SetMecanumVelocity", "SetBrushMotor"]:
            time.sleep(2)  # 2 seconds for movement functions
        else:
            time.sleep(0.5)  # 0.5 seconds for other functions
        # Find category for this function
        category = "其他"
        for cat, funcs in level1_functions_by_category.items():
            for func in funcs:
                # Handle both (method_name, params) and (method_name, params, metadata) formats
                if len(func) >= 2 and func[0] == method_name:
                    # Check if params match
                    if len(func) >= 2 and func[1] == params:
                        category = cat
                        break
            if category != "其他":
                break
        
        if category not in category_results:
            category_results[category] = {"success": 0, "fail": 0}
        
        # Validate and convert parameters for SetBrushMotor
        if method_name == "SetBrushMotor":
            # Ensure all speed values are integers and within -100 to 100 range
            validated_params = []
            for i, param in enumerate(params):
                if i % 2 == 0:  # motor_id (must be 1-4)
                    validated_params.append(int(param))
                else:  # speed (must be -100 to 100, integer)
                    speed = int(round(float(param)))
                    # Clamp to valid range
                    speed = max(-100, min(100, speed))
                    validated_params.append(speed)
            params = validated_params
        
        # Format parameters for display
        if params:
            if method_name == "ArmMoveIk" and len(params) == 7:
                params_str = f"(x={params[0]}, y={params[1]}, z={params[2]}, pitch={params[3]}, roll={params[4]}, yaw={params[5]}, speed={params[6]})"
            elif method_name == "SetMecanumVelocity" and len(params) == 3:
                params_str = f"(velocity={params[0]}, direction={params[1]}, angular_rate={params[2]})"
            elif method_name == "SetBrushMotor":
                # SetBrushMotor参数格式：motor_id1, speed1, motor_id2, speed2, ...
                motor_pairs = []
                for i in range(0, len(params), 2):
                    if i + 1 < len(params):
                        motor_pairs.append(f"motor{params[i]}={params[i+1]}")
                    else:
                        motor_pairs.append(f"motor{params[i]}=?")
                params_str = f"({', '.join(motor_pairs)})"
            else:
                params_str = f"({', '.join(str(p) for p in params)})"
        else:
            params_str = "()"
        
        # Add note from metadata if available
        note_str = ""
        if metadata.get("note"):
            note_str = f" [{metadata['note']}]"
        
        print(f"\n[{category}] Testing {method_name}{params_str}{note_str}...", end=" ")
        result = call_jsonrpc_method(ip_address, port, method_name, params, timeout)
        results[method_name] = result
        
        if result["success"]:
            # Parse the result - MasterPi returns (success_flag, data, method_name)
            if isinstance(result["result"], (list, tuple)) and len(result["result"]) >= 2:
                success_flag = result["result"][0]
                data = result["result"][1]
                method_name_returned = result["result"][2] if len(result["result"]) > 2 else method_name
                
                if success_flag:
                    print(f"✓ SUCCESS")
                    if isinstance(data, (int, float)):
                        # Format numeric results nicely
                        if method_name == "GetBatteryVoltage":
                            print(f"  Battery Voltage: {data} mV ({data/1000:.2f} V)")
                        else:
                            print(f"  Result: {data}")
                    elif data == () or data == []:
                        print(f"  Result: OK (no return data)")
                    else:
                        print(f"  Result: {data}")
                    
                    # Diagnostic: After SetMecanumVelocity, check individual motor speeds
                    if method_name == "SetMecanumVelocity":
                        # Wait a bit for motors to respond
                        time.sleep(0.3)
                        # Check each motor's speed
                        motor_speeds = {}
                        for motor_id in [1, 2, 3, 4]:
                            motor_result = call_jsonrpc_method(ip_address, port, "GetMotor", [motor_id], timeout)
                            if motor_result.get("success") and isinstance(motor_result.get("result"), (list, tuple)):
                                if len(motor_result["result"]) >= 2 and motor_result["result"][0]:
                                    motor_speeds[motor_id] = motor_result["result"][1]
                                else:
                                    motor_speeds[motor_id] = None
                            else:
                                motor_speeds[motor_id] = None
                        
                        # Display motor speeds
                        active_motors = [mid for mid, speed in motor_speeds.items() if speed is not None and abs(speed) > 5]
                        speed_str = f"M1={motor_speeds.get(1, 'N/A')}, M2={motor_speeds.get(2, 'N/A')}, M3={motor_speeds.get(3, 'N/A')}, M4={motor_speeds.get(4, 'N/A')}"
                        
                        if params == [0.0, 0.0, 0.0]:
                            # When stopping, check if all motors are actually stopped
                            non_zero = [mid for mid, speed in motor_speeds.items() if speed is not None and abs(speed) > 5]
                            if non_zero:
                                print(f"  ⚠️  WARNING: {len(non_zero)} motor(s) still running after stop command")
                                print(f"     Motor speeds: {speed_str}")
                            else:
                                print(f"  ✓ All motors stopped: {speed_str}")
                        else:
                            # When moving, check if all 4 motors are active
                            if len(active_motors) < 4:
                                print(f"  ⚠️  WARNING: Only {len(active_motors)} motor(s) active (expected 4)")
                                print(f"     Motor speeds: {speed_str}")
                                inactive = [mid for mid in [1,2,3,4] if mid not in active_motors]
                                print(f"     Inactive motors: {inactive}")
                                print(f"     Possible causes:")
                                print(f"       - Speed calculation may assign 0 to some motors")
                                print(f"       - Hardware connection issue")
                                print(f"       - Motor response difference")
                            else:
                                print(f"  ✓ All 4 motors active: {speed_str}")
                    
                    success_count += 1
                    category_results[category]["success"] += 1
                else:
                    print(f"✗ FAILED")
                    error_msg = str(data)
                    print(f"  Error: {error_msg}")
                    # 提供一些常见错误的建议
                    if method_name == "ArmMoveIk" and "E03" in error_msg:
                        print(f"  Hint: This may indicate server-side dependency issues:")
                        print(f"        - Check if 'setPitchRangeMoving' is defined in ArmIK module")
                        print(f"        - Check if 'AGC' (Action Group Control) is initialized")
                        print(f"        - The target position may also be unreachable")
                        if metadata.get("optional"):
                            print(f"  Note: This test is marked as optional - server may need setup")
                    elif method_name == "SetMecanumVelocity" and "E03" in error_msg:
                        print(f"  Hint: Check if the chassis module is initialized")
                    fail_count += 1
                    category_results[category]["fail"] += 1
            else:
                print(f"✓ SUCCESS")
                print(f"  Result: {result['result']}")
                success_count += 1
                category_results[category]["success"] += 1
        else:
            print(f"✗ ERROR")
            if isinstance(result["error"], dict):
                error_msg = result["error"].get("message", str(result["error"]))
                error_code = result["error"].get("code", "N/A")
                print(f"  Error Code: {error_code}")
                print(f"  Error Message: {error_msg}")
                # 提供参数错误的建议
                if error_code == -32602:  # Invalid params
                    print(f"  Hint: Check parameter types and format")
                    if method_name == "SetMecanumVelocity":
                        print(f"        Expected: SetMecanumVelocity(vx: float, vy: float, vw: float, time: float)")
                        print(f"        Got: {params}")
            else:
                print(f"  Error: {result['error']}")
            fail_count += 1
            category_results[category]["fail"] += 1
    
    # Print summary by category
    print("\n" + "=" * 60)
    print("Test Summary by Category:")
    print("-" * 60)
    for category, counts in category_results.items():
        total = counts["success"] + counts["fail"]
        if total > 0:
            print(f"  {category}: {counts['success']}/{total} succeeded")
    
    print("\n" + "-" * 60)
    print(f"Overall: {success_count} succeeded, {fail_count} failed (out of {len(all_functions)} tests)")
    print("=" * 60)
    
    return results


def test_basic_methods(proxy: xmlrpc.client.ServerProxy) -> Dict[str, Any]:
    """
    Test common basic methods like ping, status, etc.
    
    Args:
        proxy: XML-RPC ServerProxy
    
    Returns:
        Dictionary of test results
    """
    results = {}
    test_methods = ["ping", "status", "get_status", "health", "version", "info"]
    
    for method_name in test_methods:
        if hasattr(proxy, method_name):
            try:
                method = getattr(proxy, method_name)
                if callable(method):
                    result = method()
                    results[method_name] = {"success": True, "result": result}
                    print(f"  ✓ {method_name}(): {result}")
            except Exception as e:
                results[method_name] = {"success": False, "error": str(e)}
                print(f"  ✗ {method_name}(): {e}")
    
    return results


def main():
    """Main function with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Test and detect MasterPi robot RPC server functions"
    )
    parser.add_argument(
        "--ip",
        default=None,
        help="IP address of the robot (default: from .env ROBOT_IP, required if not in .env)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9030,
        help="Port number for RPC server (default: 9030)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Connection timeout in seconds (default: 10)"
    )
    parser.add_argument(
        "--jsonrpc",
        action="store_true",
        help="Also test JSON-RPC protocol"
    )
    parser.add_argument(
        "--test-level1",
        action="store_true",
        help="Test Level 1 (high-level) functions from MasterPi RPC server"
    )
    
    args = parser.parse_args()
    
    # Get IP from .env if not provided
    ip_address = args.ip
    if ip_address is None:
        ip_address = os.getenv("ROBOT_IP")
        if ip_address is None:
            print("Error: ROBOT_IP must be set in .env file or provided as --ip argument")
            sys.exit(1)
    
    print("=" * 60)
    print("MasterPi RPC Server Test")
    print("=" * 60)
    print()
    
    # First, detect which protocol the server uses
    print("Detecting RPC protocol...")
    protocol = detect_protocol(ip_address, args.port, args.timeout)
    
    if protocol == "jsonrpc":
        print("✓ Detected JSON-RPC protocol")
        print()
        jsonrpc_available = test_jsonrpc(ip_address, args.port, args.timeout)
        
        if jsonrpc_available:
            print()
            print("=" * 60)
            print("JSON-RPC Server Detected")
            print("=" * 60)
            
            # If --test-level1 flag is set, test Level 1 functions
            if args.test_level1:
                print()
                test_level1_results = test_level1_functions(ip_address, args.port, args.timeout)
                print()
                print("=" * 60)
                print("Level 1 Function Testing Completed")
                print("=" * 60)
            else:
                print("\n✓ JSON-RPC server is responding at the specified address.")
                print("  However, method introspection is not available.")
                print("  Please refer to the RPC server documentation for available methods.")
                print("  You can call methods using JSON-RPC format:")
                print(f"    POST http://{ip_address}:{args.port}/")
                print('    {"jsonrpc": "2.0", "method": "method_name", "params": [], "id": 1}')
                print("\n  To test Level 1 functions, use: --test-level1")
            sys.exit(0)
        else:
            print("\n✗ Could not connect to RPC server")
            print(f"  Check that the server is running at {ip_address}:{args.port}")
            sys.exit(1)
    elif protocol == "xmlrpc":
        print("✓ Detected XML-RPC protocol")
        print()
    else:
        print("? Could not detect protocol, trying both...")
        print()
    
    # Try XML-RPC first (or if protocol is unknown)
    proxy = test_xmlrpc(ip_address, args.port, args.timeout)
    
    if proxy is None:
        # Try JSON-RPC if XML-RPC failed
        print()
        jsonrpc_available = test_jsonrpc(ip_address, args.port, args.timeout)
        
        if jsonrpc_available:
            print()
            print("=" * 60)
            print("JSON-RPC Server Detected")
            print("=" * 60)
            
            # If --test-level1 flag is set, test Level 1 functions
            if args.test_level1:
                print()
                test_level1_results = test_level1_functions(ip_address, args.port, args.timeout)
                print()
                print("=" * 60)
                print("Level 1 Function Testing Completed")
                print("=" * 60)
            else:
                print("\n✓ JSON-RPC server is responding at the specified address.")
                print("  However, method introspection is not available.")
                print("  Please refer to the RPC server documentation for available methods.")
                print("  You can call methods using JSON-RPC format:")
                print(f"    POST http://{ip_address}:{args.port}/")
                print('    {"jsonrpc": "2.0", "method": "method_name", "params": [], "id": 1}')
                print("\n  To test Level 1 functions, use: --test-level1")
            sys.exit(0)
        else:
            print("\n✗ Could not connect to RPC server")
            print(f"  Check that the server is running at {ip_address}:{args.port}")
            sys.exit(1)
    
    print()
    print("-" * 60)
    print("Available Methods:")
    print("-" * 60)
    
    all_methods, user_methods = list_methods(proxy)
    
    if all_methods:
        print(f"\nAll methods ({len(all_methods)}):")
        for method in sorted(all_methods):
            sig = get_method_signature(proxy, method)
            if sig:
                print(f"  • {method}: {sig}")
            else:
                print(f"  • {method}")
        
        if user_methods:
            print(f"\nUser methods ({len(user_methods)}):")
            for method in sorted(user_methods):
                print(f"  • {method}")
    else:
        print("  (Could not retrieve method list)")
    
    print()
    print("-" * 60)
    print("Testing Basic Methods:")
    print("-" * 60)
    
    test_results = test_basic_methods(proxy)
    
    if not test_results:
        print("  (No common test methods found)")
    
    print()
    print("=" * 60)
    print("Test completed successfully!")
    print("=" * 60)
    
    sys.exit(0)


if __name__ == "__main__":
    main()

