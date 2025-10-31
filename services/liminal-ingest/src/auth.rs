//! Authentication middleware

use actix_web::{
    dev::{forward_ready, Service, ServiceRequest, ServiceResponse, Transform},
    error::ErrorUnauthorized,
    Error, HttpMessage,
};
use std::future::{ready, Ready};
use std::pin::Pin;
use std::task::{Context, Poll};
use tracing::warn;

pub struct AuthMiddleware {
    pub token: String,
}

impl<S, B> Transform<S, ServiceRequest> for AuthMiddleware
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error>,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<B>;
    type Error = Error;
    type InitError = ();
    type Transform = AuthMiddlewareService<S>;
    type Future = Ready<Result<Self::Transform, Self::InitError>>;

    fn new_transform(&self, service: S) -> Self::Future {
        ready(Ok(AuthMiddlewareService {
            service,
            token: self.token.clone(),
        }))
    }
}

pub struct AuthMiddlewareService<S> {
    service: S,
    token: String,
}

impl<S, B> Service<ServiceRequest> for AuthMiddlewareService<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error>,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<B>;
    type Error = Error;
    type Future = Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>>>>;

    forward_ready!(service);

    fn call(&self, req: ServiceRequest) -> Self::Future {
        let token = self.token.clone();

        // Skip auth for health endpoint
        if req.path() == "/health" {
            let fut = self.service.call(req);
            return Box::pin(async move { fut.await });
        }

        // Check Authorization header
        let auth_header = req
            .headers()
            .get("Authorization")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.strip_prefix("Bearer "));

        match auth_header {
            Some(t) if t == token => {
                req.extensions_mut().insert(token);
                let fut = self.service.call(req);
                Box::pin(async move { fut.await })
            }
            _ => {
                warn!("Unauthorized request to {}", req.path());
                Box::pin(async move { Err(ErrorUnauthorized("Invalid or missing token")) })
            }
        }
    }
}
