import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Layout from "../Layout";

function renderWithRouter(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>content</Layout>
    </MemoryRouter>
  );
}

describe("Layout — TTS nav entries (#151)", () => {
  it("renders sub-nav with TTS 配置 link when at /tts-config", () => {
    renderWithRouter("/tts-config");
    expect(screen.getByText("TTS 配置")).toBeInTheDocument();
  });

  it("renders TTS 配置 in sub-nav when at /config", () => {
    renderWithRouter("/config");
    expect(screen.getByText("TTS 配置")).toBeInTheDocument();
  });

  it("does not render sub-nav for non-config paths", () => {
    renderWithRouter("/");
    expect(screen.queryByText("TTS 配置")).not.toBeInTheDocument();
    expect(screen.queryByText("系统配置")).not.toBeInTheDocument();
  });

  it("renders all 4 main nav items", () => {
    renderWithRouter("/");
    expect(screen.getByTitle("项目列表")).toBeInTheDocument();
    expect(screen.getByTitle("素材库")).toBeInTheDocument();
    expect(screen.getByTitle("系统配置")).toBeInTheDocument();
    expect(screen.getByTitle("数据追踪")).toBeInTheDocument();
  });
});
