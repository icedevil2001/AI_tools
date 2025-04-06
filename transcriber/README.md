


## installation 

```bash 
uv venv 
uv sync


cd /Users/pri/git/AI_tools/transcriber
docker-compose up -d

flask run
```



Dump the database (anonymized by default):

```
python dump_db.py
```
Dump with custom output directory:
```python dump_db.py --output custom_backup```

List users instead of dumping:
```python dump_db.py --list```
List more users:
```python dump_db.py --list --count 20 ```
Skip anonymization (use with caution):
```python dump_db.py --no-anonymize```

The script includes safeguards like anonymization of sensitive user data by default, and it outputs clean, formatted JSON files that could be used for backup purposes or to migrate data to a different system.``


## ToDo
- [ ] Set cookie secure to true to enable HTTPS for production environment
## Session cookies

Looking at the logs, I see that the authentication is working correctly (the password hash matches), but there's an issue with session handling. The user is successfully authenticated, but when redirected to the index page, they get redirected back to login.

The problem is likely related to the SESSION_COOKIE_SECURE = True setting in the app configuration, which requires HTTPS. Since you're running the app locally on HTTP, the session cookie isn't being set properly.

Let's update the app.py file to fix this issue:

app.py
app.py+29-1
This change:

Sets SESSION_COOKIE_SECURE to False, which allows the session cookie to work on HTTP connections
Adds a debug route to see the session data
Adds improved debug logging in the login function
Adds a check to avoid redirection loops if the user is already logged in
This should fix the login issue while maintaining all other functionality. For a production environment, you would want to enable SESSION_COOKIE_SECURE again when running with HTTPS.