import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Icon from "@/components/ui/icon";
import { toast } from "sonner";
import UserTypeSelector from "@/components/UserTypeSelector";
import SenderForm from "@/components/SenderForm";
import CarrierForm from "@/components/CarrierForm";
import OrdersList from "@/components/OrdersList";

type UserType = "sender" | "carrier" | null;

interface SenderData {
  pickupAddress: string;
  pickupComments: string;
  warehouse: string;
  deliveryDate: string;
  cargoType: "pallet" | "box";
  cargoQuantity: string;
  senderName: string;
  phone: string;
  photo: string;
  labelSize: "120x75" | "58x40";
}

interface CarrierData {
  carBrand: string;
  carModel: string;
  licensePlate: string;
  capacityType: "pallet" | "box";
  capacityQuantity: string;
  warehouse: string;
  driverName: string;
  phone: string;
  licenseNumber: string;
  photo: string;
}

interface Order {
  id: string;
  type: "sender" | "carrier";
  data: SenderData | CarrierData;
  createdAt: Date;
}

const API_URL = "https://functions.poehali.dev/05090f07-7a7b-45e9-a7e8-33227bbce72e";

const Index = () => {
  const [userType, setUserType] = useState<UserType>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    try {
      const response = await fetch(API_URL);
      const data = await response.json();
      const formattedOrders = data.orders.map((order: any) => ({
        id: order.id.toString(),
        type: order.type,
        data: order.type === "sender" ? {
          pickupAddress: order.pickupAddress || "",
          pickupComments: order.pickupComments || "",
          warehouse: order.warehouse || "",
          deliveryDate: order.deliveryDate || "",
          cargoType: order.cargoType,
          cargoQuantity: order.cargoQuantity || "",
          senderName: order.senderName || "",
          phone: order.phone || "",
          photo: order.photo || "",
          labelSize: order.labelSize || "120x75",
        } : {
          carBrand: order.carBrand || "",
          carModel: order.carModel || "",
          licensePlate: order.licensePlate || "",
          capacityType: order.capacityType,
          capacityQuantity: order.capacityQuantity || "",
          warehouse: order.warehouse || "",
          driverName: order.driverName || "",
          phone: order.phone || "",
          licenseNumber: order.licenseNumber || "",
          photo: order.photo || "",
        },
        createdAt: new Date(order.createdAt),
      }));
      setOrders(formattedOrders);
    } catch (error) {
      console.error("Ошибка загрузки заявок:", error);
    }
  };
  const [senderData, setSenderData] = useState<SenderData>({
    pickupAddress: "",
    pickupComments: "",
    warehouse: "",
    deliveryDate: "",
    cargoType: "pallet",
    cargoQuantity: "",
    senderName: "",
    phone: "",
    photo: "",
    labelSize: "120x75",
  });
  const [carrierData, setCarrierData] = useState<CarrierData>({
    carBrand: "",
    carModel: "",
    licensePlate: "",
    capacityType: "pallet",
    capacityQuantity: "",
    warehouse: "",
    driverName: "",
    phone: "",
    licenseNumber: "",
    photo: "",
  });

  const handleSenderSubmit = async () => {
    if (!senderData.pickupAddress || !senderData.warehouse || !senderData.senderName || !senderData.phone) {
      toast.error("Заполните обязательные поля");
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "sender", ...senderData }),
      });
      
      if (response.ok) {
        toast.success("Заявка отправителя создана!");
        await loadOrders();
        setSenderData({
          pickupAddress: "",
          pickupComments: "",
          warehouse: "",
          deliveryDate: "",
          cargoType: "pallet",
          cargoQuantity: "",
          senderName: "",
          phone: "",
          photo: "",
          labelSize: "120x75",
        });
      } else {
        toast.error("Ошибка при создании заявки");
      }
    } catch (error) {
      toast.error("Ошибка сети");
    } finally {
      setLoading(false);
    }
  };

  const handleCarrierSubmit = async () => {
    if (!carrierData.carBrand || !carrierData.licensePlate || !carrierData.driverName || !carrierData.phone) {
      toast.error("Заполните обязательные поля");
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "carrier", ...carrierData }),
      });
      
      if (response.ok) {
        toast.success("Заявка перевозчика создана!");
        await loadOrders();
        setCarrierData({
          carBrand: "",
          carModel: "",
          licensePlate: "",
          capacityType: "pallet",
          capacityQuantity: "",
          warehouse: "",
          driverName: "",
          phone: "",
          licenseNumber: "",
          photo: "",
        });
      } else {
        toast.error("Ошибка при создании заявки");
      }
    } catch (error) {
      toast.error("Ошибка сети");
    } finally {
      setLoading(false);
    }
  };

  if (!userType) {
    return <UserTypeSelector onSelectType={setUserType} />;
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="bg-primary text-primary-foreground p-4 shadow-sm">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button 
              size="icon" 
              variant="ghost" 
              className="text-primary-foreground hover:bg-primary-foreground/10"
              onClick={() => setUserType(null)}
            >
              <Icon name="ArrowLeft" size={24} />
            </Button>
            <div>
              <h1 className="text-lg font-semibold">
                {userType === "sender" ? "Отправитель" : "Перевозчик"}
              </h1>
              <p className="text-sm text-primary-foreground/80">
                {userType === "sender" ? "Создание заявки на доставку" : "Регистрация перевозчика"}
              </p>
            </div>
          </div>
          <Icon name={userType === "sender" ? "PackageOpen" : "Truck"} size={28} />
        </div>
      </div>

      <div className="max-w-4xl mx-auto p-4">
        <Tabs defaultValue="form" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-6">
            <TabsTrigger value="form">Новая заявка</TabsTrigger>
            <TabsTrigger value="orders">
              Все заявки ({orders.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="form" className="animate-fade-in">
            {userType === "sender" ? (
              <SenderForm 
                senderData={senderData}
                setSenderData={setSenderData}
                onSubmit={handleSenderSubmit}
                loading={loading}
              />
            ) : (
              <CarrierForm 
                carrierData={carrierData}
                setCarrierData={setCarrierData}
                onSubmit={handleCarrierSubmit}
                loading={loading}
              />
            )}
          </TabsContent>

          <TabsContent value="orders" className="animate-fade-in">
            <OrdersList orders={orders} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default Index;
