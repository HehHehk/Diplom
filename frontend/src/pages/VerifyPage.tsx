import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { App, Button, Card, Form, Input, Result, Spin, Typography } from "antd";
import { api, apiError } from "../api/client";

type Status = "loading" | "ok" | "error";

export default function VerifyPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const token = params.get("token");
  const [status, setStatus] = useState<Status>(token ? "loading" : "error");
  const [error, setError] = useState(token ? "" : "Ссылка подтверждения отсутствует");
  const [form] = Form.useForm();

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .post("/auth/verify-email", { token })
      .then(() => {
        if (!cancelled) setStatus("ok");
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(apiError(requestError));
          setStatus("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const resend = async (values: { email: string }) => {
    try {
      const response = await api.post("/auth/resend-verification", values);
      const debugToken = response.headers["x-debug-verification-token"];
      if (debugToken) {
        message.info("Новая ссылка готова");
        navigate(`/verify?token=${encodeURIComponent(debugToken as string)}`);
      } else {
        message.success("Письмо отправлено повторно");
      }
    } catch (requestError) {
      message.error(apiError(requestError));
    }
  };

  return (
    <div className="auth-wrap">
      <Card className="auth-card">
        {status === "loading" ? (
          <div style={{ textAlign: "center", padding: 24 }}>
            <Spin size="large" />
            <Typography.Paragraph style={{ marginTop: 16 }}>
              Проверяем ссылку…
            </Typography.Paragraph>
          </div>
        ) : status === "ok" ? (
          <Result
            status="success"
            title="Email подтверждён"
            subTitle="Теперь можно войти в аккаунт."
            extra={
              <Button type="primary" onClick={() => navigate("/login")}>
                Войти
              </Button>
            }
          />
        ) : (
          <>
            <Result status="error" title="Не удалось подтвердить email" subTitle={error} />
            <Typography.Paragraph>Отправить письмо повторно:</Typography.Paragraph>
            <Form form={form} layout="inline" onFinish={resend}>
              <Form.Item
                name="email"
                rules={[{ required: true, type: "email" }]}
                style={{ flex: 1 }}
              >
                <Input placeholder="ваш email" />
              </Form.Item>
              <Button htmlType="submit">Отправить</Button>
            </Form>
          </>
        )}
      </Card>
    </div>
  );
}
