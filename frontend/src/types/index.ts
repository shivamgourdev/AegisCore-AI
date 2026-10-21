export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  createdAt: string;
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type Draft = {
  id: string;
  recipient: string;
  subject: string;
  body: string;
  status: "draft" | "pending_approval" | "approved" | "sent" | "rejected";
  providerAccepted?: boolean;
  messageId?: string;
  createdAt: string;
};

export type User = {
  id: string;
  email: string;
  createdAt: string;
};
