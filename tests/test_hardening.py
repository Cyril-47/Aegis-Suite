import sys
import os
import time

# Add parent directory to path to locate application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import auth
import utils
import audit_log

# Setup environment variables for stateless testing
os.environ["JWT_SECRET"] = "super-secret-validation-key-1234567890"

def test_jwt_tampering():
    print("[*] Running JWT Tampering test...")
    # Generate token
    token = auth.create_session(guild_id="test_guild_id_9988", role="tenant")
    print(f"    Original Token: {token}")
    
    # Decode to verify it works
    payload = auth.decode_token(token)
    assert payload is not None
    assert payload["guild_id"] == "test_guild_id_9988"
    assert payload["role"] == "tenant"
    
    # Tamper with token (changing guild_id payload)
    parts = token.split(".")
    header_b64, payload_b64, signature_b64 = parts
    
    import json
    import base64
    
    # Decode the payload
    padding = '=' * (4 - (len(payload_b64) % 4))
    payload_bytes = base64.urlsafe_b64decode((payload_b64 + padding).encode('utf-8'))
    payload_dict = json.loads(payload_bytes.decode('utf-8'))
    
    # Tamper payload
    payload_dict["guild_id"] = "99999" # Changed!
    
    # Encode back
    tampered_payload_bytes = json.dumps(payload_dict).encode('utf-8')
    tampered_payload_b64 = base64.urlsafe_b64encode(tampered_payload_bytes).rstrip(b'=').decode('utf-8')
    
    # Assemble tampered token
    tampered_token = f"{header_b64}.{tampered_payload_b64}.{signature_b64}"
    print(f"    Tampered Token: {tampered_token}")
    
    # Verify decode rejects the tampered token
    decoded = auth.decode_token(tampered_token)
    print(f"    Decoded result: {decoded}")
    assert decoded is None, "Token decoding should return None when signature mismatch occurs!"
    print("[+] JWT Tampering test passed: Signature validation successfully rejected tampered payload.")

def test_session_revocation():
    print("[*] Running Session Revocation test...")
    token = auth.create_session(guild_id="test_guild_id_9988", role="tenant")
    assert auth.validate_session(token) is True
    
    # Revoke guild
    auth.revoke_guild_sessions("test_guild_id_9988")
    assert auth.is_guild_revoked("test_guild_id_9988") is True
    
    # Verify token is now invalid
    assert auth.validate_session(token) is False, "Token should be invalid after guild revocation!"
    print("[+] Session Revocation test passed: Unlinking guild immediately invalidates existing sessions.")

def test_unrevoke_on_relink():
    print("[*] Running Un-revocation on relink test...")
    # Add to revoked list
    auth.revoke_guild_sessions("55555")
    assert auth.is_guild_revoked("55555") is True
    
    # Write a pairing code to config.json
    with utils.config_lock:
        config = utils.load_config()
        pending = config.setdefault("pending_pairings", {})
        pending["TEST99"] = {
            "guild_id": "55555",
            "guild_name": "Test Server",
            "expires_at": time.time() + 600,
            "attempts": 0
        }
        utils.save_config(config)
        
    # Retrieve guild ID by code
    gid = utils.get_guild_id_by_code("TEST99")
    assert gid == "55555"
    
    # Verify it is un-revoked
    assert auth.is_guild_revoked("55555") is False, "Guild should be un-revoked after successful dashboard login code link!"
    print("[+] Un-revocation on relink test passed.")

def test_rate_limiter():
    print("[*] Running Sliding-Window Rate Limiter test...")
    # Clean rate limits
    utils.guild_request_counts.clear()
    
    # First 60 requests should pass
    for i in range(60):
        assert utils.check_guild_rate_limit("limit_guild_1") is True, f"Request {i+1} failed"
        
    # 61st request should be blocked
    assert utils.check_guild_rate_limit("limit_guild_1") is False, "61st request should have been rate limited!"
    print("[+] Sliding-Window Rate Limiter test passed.")

def test_idempotence():
    print("[*] Running Idempotence and safe deletion test...")
    # Set up some dummy configuration in config.json
    with utils.config_lock:
        config = utils.load_config()
        guild_configs = config.setdefault("guild_configs", {})
        guild_configs["998877"] = {"dummy": "data"}
        
        sched = config.setdefault("scheduled_messages", [])
        sched.append({"id": "sched_dummy", "guild_id": "998877"})
        
        resp = config.setdefault("auto_responders", [])
        resp.append({"id": "resp_dummy", "guild_id": "998877"})
        
        utils.save_config(config)
        
    # Execute deletion logic (first time)
    def run_purge(guild_id):
        with utils.config_lock:
            config = utils.load_config()
            guild_configs = config.get("guild_configs", {})
            guild_configs.pop(guild_id, None)
            
            sched = config.get("scheduled_messages", [])
            config["scheduled_messages"] = [m for m in sched if m.get("guild_id") != guild_id]
            
            responders = config.get("auto_responders", [])
            config["auto_responders"] = [r for r in responders if r.get("guild_id") != guild_id]
            
            utils.save_config(config)
            
    # Purge first time
    run_purge("998877")
    
    # Purge second time (checking for KeyErrors or other issues)
    try:
        run_purge("998877")
    except Exception as e:
        assert False, f"Purging again threw an exception: {e}"
        
    # Verify cleaned up
    config = utils.load_config()
    assert "998877" not in config.get("guild_configs", {})
    assert not any(m.get("guild_id") == "998877" for m in config.get("scheduled_messages", []))
    assert not any(r.get("guild_id") == "998877" for r in config.get("auto_responders", []))
    print("[+] Idempotence and safe deletion test passed.")

if __name__ == "__main__":
    # Clean up test-related persistent state in config.json before running tests
    def cleanup_test_state():
        try:
            with utils.config_lock:
                config = utils.load_config()
                
                # Remove test guilds from revoked_guilds
                revoked = config.get("revoked_guilds", [])
                config["revoked_guilds"] = [g for g in revoked if g not in ["test_guild_id_9988", "55555", "998877"]]
                
                # Remove test pairings
                pending = config.get("pending_pairings", {})
                for key in ["TEST99"]:
                    pending.pop(key, None)
                    
                # Remove test configs
                guild_configs = config.get("guild_configs", {})
                for gid in ["test_guild_id_9988", "55555", "998877"]:
                    guild_configs.pop(gid, None)
                    
                utils.save_config(config)
                
            # Re-load/reset the global auth revoked guilds set to sync with the cleaned config
            auth.load_revoked_guilds()
        except Exception as e:
            print(f"Warning: Failed to clean up config.json: {e}")

    cleanup_test_state()

    try:
        test_jwt_tampering()
        test_session_revocation()
        test_unrevoke_on_relink()
        test_rate_limiter()
        test_idempotence()
        print("\n[SUCCESS] All hardening tests passed successfully!")
    except AssertionError as e:
        import traceback
        traceback.print_exc()
        print(f"\n[FAILURE] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[ERROR] Test crashed with exception: {e}")
        sys.exit(1)
    finally:
        cleanup_test_state()

