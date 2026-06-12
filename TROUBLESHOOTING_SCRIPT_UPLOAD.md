# Troubleshooting Script Upload Issues

## Quick Diagnosis

The script parser has been updated and tested successfully. If you're experiencing issues uploading scripts, please follow these steps:

### 1. Check What Error You're Seeing

**Where are you trying to upload the script?**
- [ ] Script Ingest page (`/studio/ingest`)
- [ ] Writer's Room page (worktree version with textarea)
- [ ] Study Room page

**What happens when you try?**
- [ ] Button does nothing (no response)
- [ ] Error message appears (what does it say?)
- [ ] Page loads but scenes don't appear
- [ ] Backend error in console

### 2. Verify Backend is Running

```bash
# Check if backend is running
ps aux | grep "python.*studio-backend" | grep -v grep

# If not running, start it:
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project
./start_backend.sh
```

**Expected output:** Backend should start on port 8010

### 3. Check Browser Console

1. Open browser DevTools (F12 or Cmd+Option+I)
2. Go to Console tab
3. Try uploading script again
4. Look for error messages (red text)

**Common errors:**
- `Failed to fetch` - Backend not running
- `500 Internal Server Error` - Parser error (check backend logs)
- `404 Not Found` - Wrong endpoint URL

### 4. Test Parser Directly

```bash
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project
python test_script_parser_fix.py
```

**Expected output:**
```
✅ ALL TESTS PASSED
[SCRIPT_PARSER] SCRIPT_PARSED | scenes=3 | format_detected=standard
```

### 5. Test with Simple Script

Try this minimal script first:

```
INT. COFFEE SHOP - DAY
A woman sits alone.

EXT. STREET - NIGHT
She walks outside.
```

If this works, the issue is with your specific script format.

### 6. Check Script Format

The parser now supports multiple formats:

**✅ Supported:**
```
SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone.

SCENE 2: EXT. STREET - NIGHT
She walks outside.
```

```
INT. COFFEE SHOP - DAY
A woman sits alone.

EXT. STREET - NIGHT
She walks outside.
```

```
1. Coffee Shop
A woman sits alone.

2. Street at Night
She walks outside.
```

**❌ Not Supported:**
- Scripts without any scene markers
- Scripts with only dialogue
- Scripts in non-English formats (parser looks for INT/EXT keywords)

### 7. Check Backend Logs

If backend is running, check logs for errors:

```bash
# If using start_backend.sh, logs should appear in terminal
# Look for lines starting with [SCRIPT_PARSER] or ERROR
```

### 8. Common Issues and Solutions

#### Issue: "Button does nothing"
**Solution:** Check browser console for JavaScript errors. Frontend might not be built.

```bash
cd studio-app
npm run build
```

#### Issue: "0 scenes generated"
**Solution:** Script format not recognized. Try adding INT/EXT headings:

```
INT. LOCATION - DAY
Scene content here...
```

#### Issue: "Backend not responding"
**Solution:** Restart backend:

```bash
# Kill existing backend
pkill -f "python.*studio-backend"

# Start fresh
./start_backend.sh
```

#### Issue: "Parser takes too long"
**Solution:** Very long scripts might timeout. Try splitting into smaller sections.

### 9. Verify API Endpoints

Test the generate-scenes endpoint directly:

```bash
# Create a test project first
curl -X POST http://localhost:8010/api/f51/studio/projects \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Project"}'

# Note the project_id from response, then:
curl -X POST http://localhost:8010/api/f51/studio/projects/PROJECT_ID/generate-scenes \
  -H "Content-Type: application/json" \
  -d '{"script_text": "INT. COFFEE SHOP - DAY\nA woman sits alone."}'
```

**Expected:** JSON response with scenes array

### 10. Frontend Build Check

Ensure frontend is built with latest changes:

```bash
cd studio-app
npm run build
npm test -- --run
```

**Expected:**
- Build succeeds
- All 525 tests pass

---

## Still Having Issues?

Please provide:

1. **Exact error message** (screenshot or copy-paste)
2. **Where you're trying to upload** (which page/component)
3. **Script format you're using** (first few lines)
4. **Browser console errors** (F12 → Console tab)
5. **Backend logs** (if backend is running)

With this information, I can provide a specific fix.

---

## Recent Changes

### What Was Fixed
1. ✅ Parser now recognizes "SCENE X: INT." format
2. ✅ Parser strips "SCENE X:" prefix before storing
3. ✅ Parser extracts emotional tone
4. ✅ Parser has fallback for non-standard formats
5. ✅ Frontend uses real scene descriptions in prompts

### What Wasn't Changed
- Script upload UI (should work the same)
- API endpoints (same URLs)
- Error handling (same behavior)

### Files Modified
- `studio-backend/app/services/script_parser.py` - Parser logic only
- `studio-app/src/pages/ProductionBoard.tsx` - Prompt building only

**No changes were made to:**
- Script upload forms
- API endpoint routes
- Error handling
- UI components

---

## Quick Test Script

Save this as `test_upload.sh`:

```bash
#!/bin/bash

echo "Testing script upload flow..."

# 1. Check backend
echo "1. Checking backend..."
if curl -s http://localhost:8010/health > /dev/null 2>&1; then
    echo "✅ Backend is running"
else
    echo "❌ Backend is NOT running"
    echo "   Start with: ./start_backend.sh"
    exit 1
fi

# 2. Test parser
echo "2. Testing parser..."
python test_script_parser_fix.py
if [ $? -eq 0 ]; then
    echo "✅ Parser tests pass"
else
    echo "❌ Parser tests fail"
    exit 1
fi

# 3. Test frontend build
echo "3. Testing frontend..."
cd studio-app
npm run build > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Frontend builds successfully"
else
    echo "❌ Frontend build fails"
    exit 1
fi

echo ""
echo "✅ All systems operational"
echo "   Try uploading your script now"
```

Run with: `chmod +x test_upload.sh && ./test_upload.sh`
