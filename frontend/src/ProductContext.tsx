import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useState,
} from "react";
import { api } from "./api/client";

interface ProductSummary {
	id: string;
	name: string;
}

interface ProductContextValue {
	products: ProductSummary[];
	activeProductId: string;
	activeProductName: string;
	loading: boolean;
	switchProduct: (productId: string) => Promise<void>;
	refreshProducts: () => Promise<void>;
	createProduct: (name: string) => Promise<void>;
	renameProduct: (productId: string, name: string) => Promise<void>;
	deleteProduct: (productId: string) => Promise<void>;
}

const ProductContext = createContext<ProductContextValue>({
	products: [],
	activeProductId: "",
	activeProductName: "",
	loading: false,
	switchProduct: async () => {},
	refreshProducts: async () => {},
	createProduct: async () => {},
	renameProduct: async () => {},
	deleteProduct: async () => {},
});

export function ProductProvider({ children }: { children: ReactNode }) {
	const [products, setProducts] = useState<ProductSummary[]>([]);
	const [activeProductId, setActiveProductId] = useState("");
	const [activeProductName, setActiveProductName] = useState("");
	const [loading] = useState(false);

	const refreshProducts = useCallback(async () => {
		try {
			const list = await api.listProducts();
			setProducts(list);

			// Load active product config to determine which is active
			const activeConfig = await api.getProductConfig();
			const activeId =
				((activeConfig as Record<string, unknown>).id as string) || "";
			setActiveProductId(activeId);
			const p = list.find((x) => x.id === activeId);
			setActiveProductName(
				p?.name ||
					((activeConfig as Record<string, unknown>).default_name as string) ||
					"",
			);
		} catch {
			// Products endpoint or config may not be available
			setProducts([]);
			setActiveProductId("");
			setActiveProductName("");
		}
	}, []);

	useEffect(() => {
		refreshProducts();
	}, [refreshProducts]);

	const switchProduct = useCallback(
		async (productId: string) => {
			await api.switchProduct(productId);
			await refreshProducts();
		},
		[refreshProducts],
	);

	const createProduct = useCallback(
		async (name: string) => {
			await api.createProduct(name);
			await refreshProducts();
		},
		[refreshProducts],
	);

	const renameProduct = useCallback(
		async (productId: string, name: string) => {
			await api.renameProduct(productId, name);
			await refreshProducts();
		},
		[refreshProducts],
	);

	const deleteProduct = useCallback(
		async (productId: string) => {
			await api.deleteProduct(productId);
			await refreshProducts();
		},
		[refreshProducts],
	);

	return (
		<ProductContext.Provider
			value={{
				products,
				activeProductId,
				activeProductName,
				loading,
				switchProduct,
				refreshProducts,
				createProduct,
				renameProduct,
				deleteProduct,
			}}
		>
			{children}
		</ProductContext.Provider>
	);
}

export function useProducts() {
	return useContext(ProductContext);
}
