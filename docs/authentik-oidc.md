# Sign in to Pneumatic with Authentik

1. Create an OAuth2/OpenID Provider and link it to an Authentik application.
   Select a confidential client and an RSA signing key (RS256). Set one strict
   redirect URI: `https://workflows.example.org/oauth/oidc/callback/`.
2. Assign only the users who can sign in to this workspace to the Authentik
   application. Add an OAuth2 scope mapping with scope name `groups` to the
   provider. Return only group names that can grant access to Pneumatic. Make
   sure that no other scope mapping, including `profile`, adds unfiltered
   groups. For invitations and user creation, return `email_verified: true` only
   for verified email addresses.

   Example `groups` mapping expression:

   ```python
   allowed = {"pneumatic-admins", "pneumatic-operations"}
   return {
       "groups": [group.name for group in request.user.ak_groups.all()
                  if group.name in allowed],
   }
   ```

3. Set these deployment variables. Use the exact issuer from Authentik’s OpenID
   configuration document, including any trailing slash. Set `SSO_AUTH` and
   `SSO_PROVIDER` on the backend and frontend. Keep the client secret on the
   backend.

   ```text
   SSO_AUTH=yes
   SSO_PROVIDER=oidc
   OIDC_ISSUER=https://sso.example.org/application/o/pneumatic/
   OIDC_CLIENT_ID=your-client-id
   OIDC_CLIENT_SECRET=your-client-secret
   OIDC_REDIRECT_URI=https://workflows.example.org/oauth/oidc/callback/
   OIDC_AUTO_CREATE_USERS=no
   OIDC_AUTO_LOGIN=no
   OIDC_ADMIN_GROUP=pneumatic-admins
   ```

   If Pneumatic has exactly one workspace, you can omit `OIDC_ACCOUNT_ID`. If
   Pneumatic has more than one workspace, set `OIDC_ACCOUNT_ID` to the numeric
   ID of the workspace that Authentik must manage. If Pneumatic has no
   workspaces, create one before you use OIDC.

4. Apply the backend migrations and restart Pneumatic. Test with an invited
   user. To link an existing member, first make sure that the Authentik subject
   (`sub`) belongs to that member. Then run
   `python manage.py link_oidc_user USER_ID SUBJECT` on the backend.

Pneumatic requests `openid email profile groups`. It reuses Pneumatic groups
with the same exact name and creates missing groups. A matching group can grant
access to existing workflows. Group and admin changes take effect at the next
OIDC sign-in. When `OIDC_ADMIN_GROUP` is set, only its members among OIDC-linked
users get workspace admin rights. The workspace owner keeps local access. Omit
`OIDC_ADMIN_GROUP` if Authentik must not manage workspace admin rights.

If you want Authentik users without an invitation to join, set
`OIDC_AUTO_CREATE_USERS=yes` after you test the application’s access policy.

If you want the browser to skip Pneumatic’s sign-in page, set
`OIDC_AUTO_LOGIN=yes` after you test the OIDC flow. Test the workspace owner’s
recovery sign-in at `/auth/signin/?local=1` before you enable auto-login.
