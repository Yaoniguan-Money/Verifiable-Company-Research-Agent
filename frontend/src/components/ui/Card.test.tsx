import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardTitle } from "./Card";

describe("Card", () => {
  it("渲染标题与内容", () => {
    render(
      <Card>
        <CardTitle>测试标题</CardTitle>
        <p>正文</p>
      </Card>
    );
    expect(screen.getByRole("heading", { name: "测试标题" })).toBeInTheDocument();
    expect(screen.getByText("正文")).toBeInTheDocument();
  });
});
