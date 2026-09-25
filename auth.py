from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

'''Read the token from request header'''
bearer = HTTPBearer()

'''Read the token and identify the user'''
def get_current_user(auth_info: HTTPAuthorizationCredentials = Depends(bearer)):
    users = {"alice-dev-token": "alice", "bob-dev-token": "bob"}
    user = users.get(auth_info.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

