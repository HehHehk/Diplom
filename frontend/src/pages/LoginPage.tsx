import { App, Button, Card, Form, Input, Typography } from "antd";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiError } from "../api/client";
import { useAuth } from "../auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  const onFinish = async (values: { email: string; password: string }) => {
    try {
      await login(values.email, values.password);
      message.success("Добро пожаловать");
      navigate((location.state as { from?: string })?.from ?? "/");
    } catch (error) {
      message.error(apiError(error));
    }
  };

  return (
    <div className="auth-wrap">
      <Card className="auth-card">
        <Typography.Title level={3}>Вход</Typography.Title>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: "email" }]}
          >
            <Input placeholder="admin@example.com" autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Пароль"
            rules={[{ required: true }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            Войти
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0 }}>
          Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          Демо: admin@example.com / admin12345
        </Typography.Text>
      </Card>
    </div>
  );
}
