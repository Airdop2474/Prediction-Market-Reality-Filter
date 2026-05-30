"""
app/api/routes/signal_accuracy.py
"""
from fastapi import APIRouter
from app.services.signal_tracker import get_signal_accuracy

router = APIRouter()


@router.get("/")
async def get_accuracy():
    """
    实时信号方向准确率。

    通过对比发出信号时的市场价格与当前价格，判断我们的预测方向是否正确。
    不需要等市场正式解决，可以立即评估信号质量。

    direction_accuracy: 价格朝我们预测方向移动的比例（排除 <2% 的噪音移动）
    """
    return await get_signal_accuracy()
