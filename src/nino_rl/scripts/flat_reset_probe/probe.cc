// Readback requests only: never modify joint angles, forces or velocities.
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Joint.hh>
#include <gz/sim/components/JointPosition.hh>
#include <gz/sim/components/JointVelocity.hh>
#include <gz/plugin/Register.hh>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <stdexcept>

class NinoFlatResetProbe : public gz::sim::System,
                          public gz::sim::ISystemConfigure,
                          public gz::sim::ISystemPreUpdate,
                          public gz::sim::ISystemPostUpdate {
  std::ofstream stream;
  double lastTime=-1;
 public:
  void Configure(const gz::sim::Entity &,const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &,gz::sim::EventManager &) override {
    stream.open(sdf->Get<std::string>("output"));
    if(!stream)throw std::runtime_error("Cannot open joint readback capture");
    stream<<"sim_time_s,joint,position_rad,velocity_rad_s\n"<<std::setprecision(12);
  }
  void PreUpdate(const gz::sim::UpdateInfo &,gz::sim::EntityComponentManager &ecm) override {
    ecm.Each<gz::sim::components::Joint>([&](const auto &entity,const auto *) {
      if(gz::sim::scopedName(entity,ecm,"::",false).find("::nino::")==std::string::npos)return true;
      if(!ecm.Component<gz::sim::components::JointPosition>(entity))
        ecm.CreateComponent(entity,gz::sim::components::JointPosition());
      if(!ecm.Component<gz::sim::components::JointVelocity>(entity))
        ecm.CreateComponent(entity,gz::sim::components::JointVelocity());
      return true;
    });
  }
  void PostUpdate(const gz::sim::UpdateInfo &info,const gz::sim::EntityComponentManager &ecm) override {
    double t=std::chrono::duration<double>(info.simTime).count();
    if(t==lastTime)return;lastTime=t;
    ecm.Each<gz::sim::components::Joint,gz::sim::components::JointPosition,gz::sim::components::JointVelocity>(
      [&](const auto &entity,const auto *,const auto *position,const auto *velocity) {
        auto name=gz::sim::scopedName(entity,ecm,"::",false);
        if(name.find("::nino::")==std::string::npos || position->Data().empty() || velocity->Data().empty())return true;
        stream<<t<<','<<name<<','<<position->Data()[0]<<','<<velocity->Data()[0]<<'\n';
        return true;
      });stream.flush();
  }
};
GZ_ADD_PLUGIN(NinoFlatResetProbe,gz::sim::System,gz::sim::ISystemConfigure,
             gz::sim::ISystemPreUpdate,gz::sim::ISystemPostUpdate)
