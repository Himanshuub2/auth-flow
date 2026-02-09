from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Response, status
from api.config import settings
from jose import jwt
from api.utils.logger import logger


class Auth:
    def __init__(self):
        self.jwt_secret = settings.JWT_SECRET
        self.algorithm = settings.JWT_ALGORITHM
        self.expire_min = settings.JWT_EXPIRE_MIN

    def create_jwt(self, payload):
        to_encode = payload.copy()
        expire = datetime.now(UTC) + timedelta(minutes=self.expire_min)
        to_encode["exp"] = expire
        encoded_jwt = jwt.encode(to_encode, self.jwt_secret, algorithm=self.algorithm)
        logger.debug("JWT created for sub: {}", payload.get("sub"))
        return encoded_jwt

    def verify_jwt(self, token: str):
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.algorithm])
            logger.debug("JWT verified for sub: {}", payload.get("sub"))
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.JWTClaimsError:
            logger.warning("JWT claims error")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
            )
        except jwt.JWTError as e:
            logger.error("JWT verification failed: {}", str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    def set_http_cookie(self, response: Response, token: str):
        try:
            response.set_cookie(
                key="auth_token",
                value=token,
                httponly=True,
                secure=settings.ENV == "production",
                max_age=int(timedelta(minutes=self.expire_min).total_seconds()),
                samesite="lax",
            )
            logger.debug("auth_token cookie set")
        except Exception as e:
            logger.error("Failed to set cookie: {}", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error setting cookie",
            )

    def clear_http_cookie(self, response: Response):
        try:
            response.delete_cookie(key="auth_token")
            logger.debug("auth_token cookie cleared")
        except Exception as e:
            logger.error("Failed to clear cookie: {}", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error clearing cookie",
            )


jwt_auth = Auth()
