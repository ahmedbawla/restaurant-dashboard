Deploy all recent changes in the restaurant_dashboard project to GitHub.

Follow these steps exactly:

1. Run `git status --short` in `C:\Users\ahmed\.local\bin\restaurant_dashboard` to see what has changed.

2. Stage all modified/new files EXCEPT `.streamlit/secrets.toml` and any `.env` files:
   ```
   git add -u
   git add --all -- ':!.streamlit/secrets.toml' ':!**/.env'
   ```

3. If there is nothing to commit (clean working tree), tell the user "Nothing to deploy — working tree is clean." and stop.

4. Run `git diff --cached --stat` to show the user a summary of what will be committed.

5. Generate a concise commit message that:
   - Starts with a present-tense verb (e.g. "Update", "Add", "Fix", "Improve")
   - Describes what changed at a high level based on the diff
   - Is one line, under 72 characters

6. Create the commit:
   ```
   git commit -m "<your message>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```

7. Push to origin main:
   ```
   git push origin main
   ```

8. Confirm success by printing the commit hash and a link to the GitHub repo.
