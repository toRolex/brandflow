import { Component, type ReactNode } from "react";

interface Props {
	children: ReactNode;
}

interface State {
	error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
	state: State = { error: null };

	static getDerivedStateFromError(error: Error): State {
		return { error };
	}

	render() {
		if (this.state.error) {
			return (
				<div className="min-h-40 flex items-center justify-center p-8">
					<div className="text-center">
						<div className="text-3xl mb-3">⚠️</div>
						<h2 className="text-lg font-semibold mb-2">页面出错了</h2>
						<p className="text-sm text-gray-500 mb-4">
							{this.state.error.message || "未知错误"}
						</p>
						<button
							className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"
							onClick={() => this.setState({ error: null })}
						>
							重试
						</button>
					</div>
				</div>
			);
		}
		return this.props.children;
	}
}
