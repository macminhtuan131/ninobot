// Read-only robot collision/contact capture at every 2 ms physics step.
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/plugin/Register.hh>
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include <string>

class NinoFlatContactProbe : public gz::sim::System,
                            public gz::sim::ISystemConfigure,
                            public gz::sim::ISystemPreUpdate,
                            public gz::sim::ISystemPostUpdate {
  std::ofstream stream;
 public:
  void Configure(const gz::sim::Entity &,const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &,gz::sim::EventManager &) override {
    stream.open(sdf->Get<std::string>("output"));
    if (!stream) throw std::runtime_error("Cannot open contact capture");
    stream << "sim_time_s,collision,other,points,wrench_points,max_depth_m,force_x_n,force_y_n,force_z_n,x_m,y_m,z_m,roll_rad,pitch_rad,yaw_rad\n";
    stream << std::setprecision(12);
  }
  void PreUpdate(const gz::sim::UpdateInfo &,gz::sim::EntityComponentManager &ecm) override {
    ecm.Each<gz::sim::components::Collision>([&](const auto &entity,const auto *) {
      auto name=gz::sim::scopedName(entity,ecm,"::",false);
      if (name.find("::nino::")!=std::string::npos &&
          !ecm.Component<gz::sim::components::ContactSensorData>(entity))
        ecm.CreateComponent(entity,gz::sim::components::ContactSensorData());
      return true;
    });
  }
  void PostUpdate(const gz::sim::UpdateInfo &info,const gz::sim::EntityComponentManager &ecm) override {
    if(info.paused)return;
    double t=std::chrono::duration<double>(info.simTime).count();
    ecm.Each<gz::sim::components::Collision,gz::sim::components::ContactSensorData>(
      [&](const auto &entity,const auto *,const auto *data) {
        auto name=gz::sim::scopedName(entity,ecm,"::",false);
        if(name.find("::nino::")==std::string::npos)return true;
        auto pose=gz::sim::worldPose(entity,ecm);
        auto write=[&](const std::string &other,int points,int wpoints,double depth,double fx,double fy,double fz) {
          stream<<t<<','<<name<<','<<other<<','<<points<<','<<wpoints<<','<<depth<<','<<fx<<','<<fy<<','<<fz<<','
            <<pose.Pos().X()<<','<<pose.Pos().Y()<<','<<pose.Pos().Z()<<','
            <<pose.Rot().Roll()<<','<<pose.Rot().Pitch()<<','<<pose.Rot().Yaw()<<'\n';
        };
        if(!data->Data().contact_size())write("none",0,0,0,0,0,0);
        for(const auto &c:data->Data().contact()) {
          bool first=c.collision1().id()==entity;
          double depth=0,fx=0,fy=0,fz=0;
          for(auto d:c.depth())depth=std::max(depth,d);
          for(const auto &w:c.wrench()) {
            const auto &force=first?w.body_1_wrench().force():w.body_2_wrench().force();
            fx+=force.x();fy+=force.y();fz+=force.z();
          }
          write(first?c.collision2().name():c.collision1().name(),c.position_size(),c.wrench_size(),depth,fx,fy,fz);
        }
        return true;
      });
    stream.flush();
  }
};
GZ_ADD_PLUGIN(NinoFlatContactProbe,gz::sim::System,gz::sim::ISystemConfigure,
              gz::sim::ISystemPreUpdate,gz::sim::ISystemPostUpdate)
