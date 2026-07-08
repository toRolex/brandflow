from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Request

from packages.provider_config.app_config import AppConfigManager

router = APIRouter(tags=["products"])


class CreateProductBody(BaseModel):
    name: str


class RenameProductBody(BaseModel):
    name: str


def _app_config(request: Request) -> AppConfigManager:
    return AppConfigManager(config_dir=str(request.app.state.root_dir / "config"))


@router.get("/api/products")
def list_products(request: Request) -> list[dict[str, str]]:
    """返回所有产品的 id + name 摘要。"""
    return _app_config(request).list_products()


@router.post("/api/products")
def create_product(request: Request, body: CreateProductBody) -> dict[str, str]:
    """新建产品。"""
    cfg = _app_config(request)
    try:
        return cfg.create_product(body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/products/{product_id}")
def rename_product(request: Request, product_id: str, body: RenameProductBody) -> dict[str, str]:
    """重命名产品。"""
    cfg = _app_config(request)
    try:
        return cfg.rename_product(product_id, body.name)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/products/{product_id}")
def delete_product(request: Request, product_id: str) -> dict:
    """删除产品。"""
    cfg = _app_config(request)
    try:
        return cfg.delete_product(product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/products/{product_id}/switch")
def switch_product(request: Request, product_id: str) -> dict:
    """切换到指定产品，不存在时自动创建。"""
    cfg = _app_config(request)
    cfg.switch_product(product_id)
    raw = cfg._load()
    return {
        "active_product_id": raw.get("active_product_id", product_id),
    }


@router.get("/api/products/{product_id}/config")
def get_product_config(request: Request, product_id: str) -> dict:
    """读取指定产品的完整配置。"""
    cfg = _app_config(request)
    # 验证产品存在
    products = cfg.list_products()
    if not any(p["id"] == product_id for p in products):
        raise HTTPException(status_code=404, detail="product not found")
    return cfg.get_product_config(product_id)


@router.put("/api/products/{product_id}/config")
def update_product_config(request: Request, product_id: str, payload: dict) -> dict:
    """更新指定产品的配置。"""
    cfg = _app_config(request)
    # 验证产品存在
    products = cfg.list_products()
    if not any(p["id"] == product_id for p in products):
        raise HTTPException(status_code=404, detail="product not found")

    cfg.save_product_config(product_id, payload)
    return cfg.get_product_config(product_id)
