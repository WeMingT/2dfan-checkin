"""邮件通知模块"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional


def send_email(
    subject: str,
    body: str,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    to_email: str,
    use_ssl: bool = True
) -> bool:
    """
    发送邮件通知

    Args:
        subject: 邮件主题
        body: 邮件正文
        smtp_server: SMTP 服务器地址
        smtp_port: SMTP 端口
        smtp_user: 发件人邮箱
        smtp_pass: SMTP 授权码
        to_email: 收件人邮箱
        use_ssl: 是否使用 SSL（默认 True）

    Returns:
        发送成功返回 True，失败返回 False
    """
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False


def format_checkin_result(user_id: str, result) -> str:
    """
    格式化单个用户的签到结果

    Args:
        user_id: 用户 ID
        result: 签到结果对象

    Returns:
        格式化后的文本
    """
    if hasattr(result, 'checkins_count') and result.checkins_count is not None and result.checkins_count > 0:
        return f"用户 {user_id}: 签到成功，累计 {result.checkins_count} 天，连续 {result.serial_checkins} 天"
    elif hasattr(result, 'error') and result.error:
        return f"用户 {user_id}: {result.error}"
    else:
        return f"用户 {user_id}: 签到结果未知"


def build_notification(results: list[tuple[str, any]]) -> tuple[str, str]:
    """
    构建通知邮件的主题和正文

    Args:
        results: [(user_id, result), ...] 签到结果列表

    Returns:
        (subject, body) 元组
    """
    # 新签到成功：有累计天数的才算真正成功
    new_success_count = sum(
        1 for _, r in results
        if hasattr(r, 'checkins_count') and r.checkins_count is not None and r.checkins_count > 0
    )
    # 今日已签到：error 中包含"已签到"
    already_count = sum(
        1 for _, r in results
        if hasattr(r, 'error') and r.error and '已签到' in r.error
    )
    total_count = len(results)
    failed_count = total_count - new_success_count - already_count

    # 根据签到情况确定邮件主题
    if new_success_count == total_count:
        # 所有用户都是新签到成功
        subject = "[2dfan] 签到成功"
    elif new_success_count > 0 and failed_count == 0:
        # 有新签到成功，没有失败（可能有已签到）
        subject = f"[2dfan] 签到成功 ({new_success_count}/{total_count})"
    elif already_count == total_count:
        # 所有用户都是今日已签到（明确区分）
        subject = "[2dfan] 今日已签到"
    elif failed_count > 0:
        # 有失败的情况
        subject = "[2dfan] 签到失败"
    else:
        subject = "[2dfan] 签到结果"

    body_lines = [format_checkin_result(uid, r) for uid, r in results]
    body = "\n".join(body_lines)

    return subject, body


def send_checkin_notification(
    results: list[tuple[str, any]],
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
    notify_email: Optional[str] = None
) -> bool:
    """
    发送签到结果通知

    Args:
        results: [(user_id, result), ...] 签到结果列表
        smtp_server: SMTP 服务器（可选，默认从环境变量获取）
        smtp_port: SMTP 端口（可选，默认从环境变量获取）
        smtp_user: 发件人（可选，默认从环境变量获取）
        smtp_pass: SMTP 授权码（可选，默认从环境变量获取）
        notify_email: 收件人（可选，默认从环境变量获取）

    Returns:
        发送成功返回 True，未配置或失败返回 False
    """
    import os

    smtp_server = smtp_server or os.environ.get('SMTP_SERVER')
    if not smtp_server:
        return False

    smtp_port = smtp_port or int(os.environ.get('SMTP_PORT', '465'))
    smtp_user = smtp_user or os.environ.get('SMTP_USER')
    smtp_pass = smtp_pass or os.environ.get('SMTP_PASS')
    notify_email = notify_email or os.environ.get('NOTIFY_EMAIL')

    if not all([smtp_user, smtp_pass, notify_email]):
        print("邮件通知配置不完整，跳过发送")
        return False

    subject, body = build_notification(results)

    return send_email(
        subject=subject,
        body=body,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        to_email=notify_email
    )
